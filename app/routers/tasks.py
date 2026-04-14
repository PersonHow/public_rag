"""
app/routers/tasks.py

POST /internal/tasks/process-document — Cloud Tasks Worker 端點。

X-Internal-Token header 驗證。
Worker 開頭先檢查 session status，若已是 failed 直接回 200。

完整處理路徑（已更新）：
  docx  → python-docx → Gemini Flash（文字）→ 存 converted/ → chunks 寫 DB
  pdf   → Gemini Flash（PDF 直讀，視覺理解）→ 存 converted/ → chunks 寫 DB
  tap/nc → 更新 document status，不建立 chunks
  dxf    → 更新 document status，不處理
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.session import IngestionSession
from app.services import gcs as gcs_service
from app.services.detector import is_code_file, is_skip_file
from app.services.gemini import (
    GeminiMaxRetriesError,
    PdfConversionResult,
    convert_pdf_to_chunks,
    convert_to_chunks,
)
from app.services.parser import parse_docx

router = APIRouter(prefix="/internal/tasks", tags=["internal"])
settings = get_settings()
logger = get_logger("tasks")

class ProcessDocumentRequest(BaseModel):
    session_id: str
    doc_id: str
    doc_type: str
    company_id: str

def _verify_internal_token(x_internal_token: str = Header(alias="X-Internal-Token")) -> None:
    """X-Internal-Token 驗證。"""
    if x_internal_token != settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="無效的 X-Internal-Token")


@router.post("/process-document")
async def process_document(
    body:ProcessDocumentRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_internal_token),
) -> dict:
    """
    Cloud Tasks Worker 主端點。
    接收 { session_id, doc_id, doc_type, company_id }。
    """
    session_id = uuid.UUID(body.session_id)
    doc_id = uuid.UUID(body.doc_id)
    doc_type: str = body.doc_type
    company_id: str = body.company_id

    log_extra = {"session_id": str(session_id), "doc_id": str(doc_id), "company_id": company_id}

    # ── Worker 開頭檢查 status ───────────────────────────────────────────
    session_result = await db.execute(
        select(IngestionSession).where(IngestionSession.session_id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        logger.error("Session 不存在", extra=log_extra)
        return {"status": "error", "message": "Session 不存在"}

    if session.status == "failed":
        logger.info("Session 已是 failed，停止 Cloud Tasks 重試", extra=log_extra)
        return {"status": "skipped", "message": "session already failed"}

    # ── 取 document ──────────────────────────────────────────────────────
    doc_result = await db.execute(
        select(Document).where(Document.doc_id == doc_id)
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        logger.error("Document 不存在", extra=log_extra)
        return {"status": "error", "message": "Document 不存在"}

    try:
        await _route_document(
            session=session,
            document=document,
            doc_type=doc_type,
            company_id=company_id,
            db=db,
            log_extra=log_extra,
        )
        await db.flush()
        return {"status": "ok"}

    except GeminiMaxRetriesError as e:
        await _mark_session_failed(session, db, reason=str(e), log_extra=log_extra)
        await db.flush()
        # 回傳 200：避免 Cloud Tasks 繼續重試
        return {"status": "failed", "message": str(e)}

    except Exception as e:
        logger.error(f"Worker 未預期錯誤: {e}", extra=log_extra)
        await _mark_session_failed(session, db, reason=f"unexpected: {e}", log_extra=log_extra)
        await db.flush()
        return {"status": "error", "message": str(e)}


async def _route_document(
    session: IngestionSession,
    document: Document,
    doc_type: str,
    company_id: str,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    """文件類型路由。"""

    # ── tap / nc：存 GCS 路徑，不進向量庫 ──────────────────────────────
    if is_code_file(doc_type):
        document.status = "gcs_stored"
        session.status = "pending_preview"
        logger.info(f"{doc_type.upper()} 檔案已存 GCS 路徑，跳過向量化", extra=log_extra)
        return

    # ── dxf / unknown：v1 不處理 ─────────────────────────────────────
    if is_skip_file(doc_type):
        document.status = "skipped"
        session.status = "pending_preview"
        logger.info(f"{doc_type} 檔案 v1 不處理，存 GCS 保留", extra=log_extra)
        return

    # ── 下載原始檔 ────────────────────────────────────────────────────
    gcs_path = document.gcs_raw_path
    file_bytes = await gcs_service.download_bytes(gcs_path)

    # ── docx：python-docx 提取文字 → Gemini Flash（文字模式）────────
    if doc_type == "docx":
        structured = parse_docx(file_bytes)
        await _run_gemini_text_and_save(
            structured=structured,
            session=session,
            document=document,
            company_id=company_id,
            db=db,
            log_extra=log_extra,
        )
        return

    # ── pdf：Gemini Flash 直讀（視覺理解，不分掃描/文字型）──────────
    if doc_type == "pdf":
        logger.info("PDF 直送 Gemini Flash 視覺理解", extra=log_extra)
        await _run_gemini_pdf_and_save(
            file_bytes=file_bytes,
            session=session,
            document=document,
            company_id=company_id,
            db=db,
            log_extra=log_extra,
        )
        return

    # ── 未知類型（防禦）──────────────────────────────────────────────
    logger.warning(f"未知 doc_type: {doc_type}，跳過", extra=log_extra)
    document.status = "skipped"
    session.status = "pending_preview"


async def _run_gemini_pdf_and_save(
    file_bytes: bytes,
    session: IngestionSession,
    document: Document,
    company_id: str,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    """
    PDF 路徑：Gemini Flash 直讀 → 更新 quality flag → 存 converted/ → 寫 chunks DB。
    GeminiMaxRetriesError 往上拋，由 process_document 捕捉。
    """
    session_id = str(session.session_id)
    doc_id = str(document.doc_id)

    result: PdfConversionResult = await convert_pdf_to_chunks(
        file_bytes=file_bytes,
        session_id=session_id,
        doc_id=doc_id,
    )

    # quality flag 寫入 documents 表
    # has_low_confidence 欄位沿用，語意調整為「Gemini 標記品質疑慮」
    # min_confidence 填 None（Gemini 不給數值分數）
    document.has_low_confidence = result.has_quality_issue
    document.min_confidence = None
    document.status = "gemini_processed"

    # quality_note 存 GCS processed/（供 debug 查閱，15 天後自動刪除）
    if result.has_quality_issue and result.quality_note:
        quality_gcs_path = settings.gcs_processed_path(company_id, session_id)
        await gcs_service.upload_json(
            quality_gcs_path,
            {"has_quality_issue": True, "quality_note": result.quality_note},
        )

    await _save_chunks_to_db(
        chunk_outputs=result.chunks,
        session=session,
        document=document,
        company_id=company_id,
        db=db,
        log_extra=log_extra,
    )


async def _run_gemini_text_and_save(
    structured: dict,
    session: IngestionSession,
    document: Document,
    company_id: str,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    """
    DOCX 路徑：Gemini Flash 文字模式 → 存 converted/ → 寫 chunks DB。
    GeminiMaxRetriesError 往上拋，由 process_document 捕捉。
    """
    session_id = str(session.session_id)
    doc_id = str(document.doc_id)

    chunk_outputs = await convert_to_chunks(
        structured_text=structured,
        session_id=session_id,
        doc_id=doc_id,
    )

    # DOCX 無 OCR，confidence 欄位填 null
    document.has_low_confidence = None
    document.min_confidence = None
    document.status = "gemini_processed"

    await _save_chunks_to_db(
        chunk_outputs=chunk_outputs,
        session=session,
        document=document,
        company_id=company_id,
        db=db,
        log_extra=log_extra,
    )


async def _save_chunks_to_db(
    chunk_outputs: list,
    session: IngestionSession,
    document: Document,
    company_id: str,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    """chunks 存 GCS converted/ + 寫 Cloud SQL（兩條路徑共用）。"""
    session_id = str(session.session_id)

    # 存 converted/ GCS（永久保留）
    converted_gcs_path = settings.gcs_converted_path(company_id, session_id)
    await gcs_service.upload_json(
        converted_gcs_path,
        [c.model_dump() for c in chunk_outputs],
    )

    # rule_version（Phase 3 從 company_rules 取，v1 用時間戳產生）
    rule_version = _generate_rule_version()
    session.rule_version_used = rule_version

    # 寫 chunks 到 Cloud SQL
    for chunk_output in chunk_outputs:
        chunk = Chunk(
            doc_id=document.doc_id,
            company_id=company_id,
            rule_version=rule_version,
            doc_type=chunk_output.doc_type,
            embed_text=chunk_output.embed_text,
            product_name=chunk_output.product_name,
            product_id=chunk_output.product_id,
            material=chunk_output.material,
            dimensions=chunk_output.dimensions,
            specs=chunk_output.specs,
            situation=chunk_output.situation,
            action=chunk_output.action,
            reason=chunk_output.reason,
            applies_to=chunk_output.applies_to,
            case_id=chunk_output.case_id,
            code_gcs_path=None,       # Phase 4 後處理注入
            drawing_gcs_path=None,    # Phase 4 後處理注入
        )
        db.add(chunk)

    document.status = "converted"
    session.status = "pending_preview"

    logger.info(
        "chunks 寫入 DB 完成",
        extra={
            **log_extra,
            "chunk_count": len(chunk_outputs),
            "rule_version": rule_version,
            "converted_gcs_path": converted_gcs_path,
        },
    )


async def _mark_session_failed(
    session: IngestionSession,
    db: AsyncSession,
    reason: str,
    log_extra: dict,
) -> None:
    session.status = "failed"
    session.fail_reason = reason[:500]
    logger.error(f"Session 標記為 failed: {reason}", extra=log_extra)


def _generate_rule_version() -> str:
    """
    生成 rule_version，格式：v1-YYMMDD-HHMM。
    Phase 3 改為從 company_rules 取最新版本。
    """
    now = datetime.now(timezone.utc)
    return now.strftime("v1-%y%m%d-%H%M")
