"""
app/routers/internal/tasks.py

POST /internal/tasks/process-document  — Cloud Tasks Worker，Gemini 格式轉換
POST /internal/tasks/ingest-chunks     — Phase 4：向量化 + 寫入 Qdrant（X-Internal-Token）
POST /internal/tasks/inject-gcs-paths  — Phase 4：TAP 路徑注入（X-Internal-Token）

X-Internal-Token header 驗證。
Worker 開頭先檢查 session status，若已是 failed 直接回 200。

Phase 3 變更：
  - process_document 開始時從 DB 取得 company + latest rules，組成 company_context
  - company_context 沿著呼叫鏈傳入 gemini 函式
  - rule_version 優先從 company_rules 取，沒有設定 rules 才 fallback 用時間戳

Phase 4 變更：
  - _save_chunks_to_db 新增 face 欄位
  - 新增 ingest_chunks endpoint（從 SQL 讀 chunks → 向量化 → Qdrant upsert）
  - 新增 inject_gcs_paths endpoint（TAP 路徑注入，全公司範圍，可隨時重跑）

Phase 5 變更：
  -新增 chunk_index（enumerate 保留文件內順序）。
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.company import Company
from app.models.document import Document
from app.models.session import IngestionSession
from app.services.storage import gcs as gcs_service
from app.services.document.detector import is_code_file, is_skip_file
from app.services.ai.embedding import embed_texts
from app.services.ai.gemini import (
    GeminiMaxRetriesError,
    PdfConversionResult,
    convert_pdf_to_chunks,
    convert_to_chunks,
)
from app.services.document.parser import parse_docx
from app.services.ai.qdrant_service import delete_chunks_by_ids, upsert_chunks
from app.services.rules import get_latest_rules, generate_rule_version

router = APIRouter(prefix="/internal/tasks", tags=["internal"])
settings = get_settings()
logger = get_logger("tasks")

# ── TAP 面向 → 檔名後綴對照表 ────────────────────────────────────────────────
# 注入時將 chunk.face 轉換成 TAP 檔名後綴（奇賓機械慣例 + 常見命名）
# key 統一小寫，查找時一律 .lower() 比對（大小寫不敏感）
_FACE_TO_SUFFIX: dict[str, str] = {
    "第一面": "_A_",
    "面a": "_A_",
    "op10": "_A_",
    "第二面": "_B_",
    "面b": "_B_",
    "op20": "_B_",
}


def _get_face_suffix(face: str) -> str:
    """大小寫不敏感的 face → TAP 檔名後綴查找。未知值記錄 warning 並回傳空字串。"""
    result = _FACE_TO_SUFFIX.get(face.lower())
    if result is None:
        logger.warning(f"未知的 face 值: {face!r}，無法比對 TAP 後綴，fallback 不限面向")
    return result or ""


# ── Request / Response Schemas ────────────────────────────────────────────────

class ProcessDocumentRequest(BaseModel):
    session_id: uuid.UUID
    doc_id: uuid.UUID
    doc_type: str
    company_id: uuid.UUID


class IngestChunksRequest(BaseModel):
    session_id: uuid.UUID


class InjectGcsPathsRequest(BaseModel):
    company_id: uuid.UUID


# ── Token 驗證 ────────────────────────────────────────────────────────────────

def _verify_internal_token(x_internal_token: str = Header(..., alias="X-Internal-Token")) -> None:
    if x_internal_token != settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="無效的 X-Internal-Token")


# ── /process-document ─────────────────────────────────────────────────────────

@router.post("/process-document")
async def process_document(
    body: ProcessDocumentRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_internal_token),
) -> dict:
    session_id: uuid.UUID = body.session_id
    doc_id: uuid.UUID = body.doc_id
    doc_type: str = body.doc_type
    company_id_str: str = str(body.company_id)

    log_extra = {"session_id": str(session_id), "doc_id": str(doc_id), "company_id": company_id_str}

    # ── 1. 檢查 session ──────────────────────────────────────────────────
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

    # ── 2. 取 document ───────────────────────────────────────────────────
    doc_result = await db.execute(
        select(Document).where(Document.doc_id == doc_id)
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        logger.error("Document 不存在", extra=log_extra)
        return {"status": "error", "message": "Document 不存在"}

    # ── 3. 取 company + latest rules（Phase 3 新增）──────────────────────
    company_context = await _build_company_context(db, session.company_id)

    try:
        await _route_document(
            session=session,
            document=document,
            doc_type=doc_type,
            company_context=company_context,
            db=db,
            log_extra=log_extra,
        )
        await db.flush()
        return {"status": "ok"}

    except GeminiMaxRetriesError as e:
        await _mark_session_failed(session, db, reason=str(e), log_extra=log_extra)
        await db.flush()
        return {"status": "failed", "message": str(e)}

    except Exception as e:
        logger.error(f"Worker 未預期錯誤: {e}", extra=log_extra)
        await _mark_session_failed(session, db, reason=f"unexpected: {e}", log_extra=log_extra)
        await db.flush()
        return {"status": "error", "message": str(e)}


# ── /ingest-chunks ────────────────────────────────────────────────────────────

@router.post("/ingest-chunks")
async def ingest_chunks(
    body: IngestChunksRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_internal_token),
) -> dict:
    """
    Phase 4 向量寫入 worker。
    流程：從 SQL 讀 chunks → embed_texts → upsert Qdrant → session done

    Option A 設計（chunks 已在 SQL 中）：
    - 直接查 SQL，不重新讀 GCS
    - 冪等：重複執行只是 upsert 覆蓋，不會重複 INSERT
    """
    session_id: uuid.UUID = body.session_id
    log_extra = {"session_id": str(session_id)}

    # ── 1. 檢查 session（FOR UPDATE 防止並發重複處理）────────────────────
    session_result = await db.execute(
        select(IngestionSession)
        .where(IngestionSession.session_id == session_id)
        .with_for_update()
    )
    session = session_result.scalar_one_or_none()
    if not session:
        logger.error("Session 不存在", extra=log_extra)
        return {"status": "error", "message": "Session 不存在"}

    company_id_str = str(session.company_id)
    log_extra["company_id"] = company_id_str

    # 非 confirmed 狀態不處理（已 done 或 processing 中的重試保護）
    if session.status not in ("confirmed", "processing"):
        logger.info(
            f"Session 狀態 {session.status}，跳過 ingest-chunks",
            extra=log_extra,
        )
        return {"status": "skipped", "message": f"session status is {session.status}"}

    # ── 2. 取該 session 所有 chunks（從 SQL）────────────────────────────
    docs_result = await db.execute(
        select(Document.doc_id).where(Document.session_id == session_id)
    )
    doc_ids = [row[0] for row in docs_result.all()]

    if not doc_ids:
        logger.warning("Session 沒有任何 document，跳過", extra=log_extra)
        session.status = "done"
        await db.flush()
        return {"status": "ok", "chunk_count": 0}

    chunks_result = await db.execute(
        select(Chunk).where(Chunk.doc_id.in_(doc_ids))
    )
    chunks = list(chunks_result.scalars().all())

    if not chunks:
        logger.warning("Session 沒有任何 chunk，跳過", extra=log_extra)
        session.status = "done"
        await db.flush()
        return {"status": "ok", "chunk_count": 0}

    logger.info(f"ingest-chunks 開始", extra={**log_extra, "chunk_count": len(chunks)})
    session.status = "processing"
    await db.flush()

    # 預先收集 chunk_ids，供 Qdrant rollback 使用
    chunk_ids = [str(c.chunk_id) for c in chunks]

    # ── 3. 批次向量化 ────────────────────────────────────────────────────
    try:
        embed_text_list = [c.embed_text for c in chunks]
        vectors = await embed_texts(embed_text_list, task_type="RETRIEVAL_DOCUMENT")
    except Exception as e:
        logger.error(f"embed_texts 失敗: {e}", extra=log_extra)
        await _mark_session_failed(session, db, reason=f"embedding failed: {e}", log_extra=log_extra)
        await db.flush()
        return {"status": "failed", "message": str(e)}

    # ── 4. 組裝 Qdrant points ────────────────────────────────────────────
    points = [
        {
            "id": str(c.chunk_id),
            "vector": vectors[i],
            "payload": {
                "company_id": str(c.company_id),
                "chunk_id": str(c.chunk_id),
                "doc_id": str(c.doc_id),
                "doc_type": c.doc_type,
                "rule_version": c.rule_version,
                "face": c.face,
                "product_name": c.product_name,
                "product_id": c.product_id,
                "situation": c.situation,
                "action": c.action,
                "embed_text": c.embed_text,  # 保留供 debug
            },
        }
        for i, c in enumerate(chunks)
    ]

    # ── 5. Upsert Qdrant（失敗時回滾已寫入的向量）────────────────────────
    try:
        upsert_chunks(points)
    except Exception as e:
        logger.error(f"Qdrant upsert 失敗，嘗試回滾: {e}", extra=log_extra)
        try:
            delete_chunks_by_ids(chunk_ids)
        except Exception as rollback_err:
            logger.error(f"Qdrant rollback 失敗: {rollback_err}", extra=log_extra)
        await _mark_session_failed(session, db, reason=f"qdrant upsert failed: {e}", log_extra=log_extra)
        await db.flush()
        return {"status": "failed", "message": str(e)}

    # ── 6. 完成 ──────────────────────────────────────────────────────────
    session.status = "done"
    await db.flush()

    logger.info(
        "ingest-chunks 完成",
        extra={**log_extra, "chunk_count": len(chunks), "phase": "phase4"},
    )
    return {"status": "ok", "chunk_count": len(chunks)}


# ── /inject-gcs-paths ────────────────────────────────────────────────────────

@router.post("/inject-gcs-paths")
async def inject_gcs_paths(
    body: InjectGcsPathsRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_internal_token),
) -> dict:
    """
    Phase 4 TAP 路徑注入。
    對指定 company 的所有 chunks 補入 code_gcs_path。
    設計為冪等：可隨時重跑，不影響已正確注入的 chunks。
    範圍：全公司（不限 session），解決跨 session 分批上傳問題。

    比對邏輯：
      1. product_id in TAP filename（主鍵比對）
      2. face → 檔名後綴（_A_ / _B_）精準對應
      3. 無法比對 face → fallback 取同 product_id 最新上傳的 TAP
      4. 找不到 TAP → code_gcs_path 保持 null
    """
    company_id: uuid.UUID = body.company_id
    company_id_str = str(company_id)
    log_extra = {"company_id": company_id_str, "phase": "phase4"}

    # ── 1. 取全公司所有 TAP/NC documents ────────────────────────────────
    tap_docs_result = await db.execute(
        select(Document).where(
            Document.company_id == company_id,
            Document.doc_type.in_(["tap", "nc"]),
        )
    )
    tap_docs = list(tap_docs_result.scalars().all())

    if not tap_docs:
        logger.info("該公司無 TAP/NC 文件，跳過注入", extra=log_extra)
        return {"status": "ok", "injected_count": 0}

    # ── 2. 建立 TAP 快查表 ────────────────────────────────────────────────
    # tap_by_product_id: { product_id_fragment: [Document, ...] }（依 created_at desc 排序）
    # 注意：TAP 的 product_id 在 gcs_raw_path 的最後一段檔名裡
    tap_map: dict[str, list[Document]] = {}
    for doc in sorted(tap_docs, key=lambda d: d.created_at, reverse=True):
        filename = doc.gcs_raw_path.split("/")[-1]
        tap_map.setdefault(filename, []).append(doc)

    logger.info(
        f"TAP/NC 文件載入完成",
        extra={**log_extra, "tap_count": len(tap_docs)},
    )

    # ── 3. 取全公司 code_gcs_path = null 且有 product_id 的 chunks ──────
    chunks_result = await db.execute(
        select(Chunk).where(
            Chunk.company_id == company_id,
            Chunk.product_id.isnot(None),
            Chunk.code_gcs_path.is_(None),
        )
    )
    chunks = list(chunks_result.scalars().all())

    if not chunks:
        logger.info("無需注入的 chunks（已全部有 code_gcs_path 或無 product_id）", extra=log_extra)
        return {"status": "ok", "injected_count": 0}

    # ── 4. 比對 + 注入 ────────────────────────────────────────────────────
    injected_count = 0

    for chunk in chunks:
        pid = chunk.product_id  # e.g. "A034-189010-1"
        target_suffix = _get_face_suffix(chunk.face) if chunk.face else ""

        matched_doc: Optional[Document] = None

        # 精準比對：product_id in filename + face suffix
        for filename, docs in tap_map.items():
            if pid not in filename:
                continue
            if target_suffix and target_suffix in filename:
                matched_doc = docs[0]  # 已按 created_at desc 排序，取最新
                break
            # 暫存 fallback（product_id 符合但 face 沒比到）
            if not matched_doc:
                matched_doc = docs[0]

        # 有 face 但沒比到精準 → 使用 fallback（已設在上方），記錄 warning
        if chunk.face and target_suffix and matched_doc:
            matched_filename = matched_doc.gcs_raw_path.split("/")[-1]
            if target_suffix not in matched_filename:
                logger.warning(
                    f"face 精準比對失敗，使用 fallback TAP",
                    extra={
                        **log_extra,
                        "chunk_id": str(chunk.chunk_id),
                        "product_id": pid,
                        "face": chunk.face,
                        "fallback_file": matched_filename,
                    },
                )

        if matched_doc:
            chunk.code_gcs_path = matched_doc.gcs_raw_path
            injected_count += 1

    await db.flush()

    logger.info(
        "inject-gcs-paths 完成",
        extra={**log_extra, "injected_count": injected_count, "total_chunks": len(chunks)},
    )
    return {
        "status": "ok",
        "injected_count": injected_count,
        "total_chunks": len(chunks),
    }


# ── 共用輔助函式 ──────────────────────────────────────────────────────────────

async def _build_company_context(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """
    取得 company 資訊 + 最新 rules，組成 company_context dict。
    rules 為 None 表示該公司尚未設定，Gemini 會用通用 prompt。
    """
    company_result = await db.execute(
        select(Company).where(Company.company_id == company_id)
    )
    company = company_result.scalar_one_or_none()

    latest_rule = await get_latest_rules(db, company_id)

    return {
        "company_name": company.name if company else "",
        "industry": (company.industry or "") if company else "",
        "rules": latest_rule.field_mapping if latest_rule else None,
        "rule_version": latest_rule.rule_version if latest_rule else generate_rule_version(),
    }


async def _route_document(
    session: IngestionSession,
    document: Document,
    doc_type: str,
    company_context: dict,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    """文件類型路由。"""

    if is_code_file(doc_type):
        document.status = "gcs_stored"
        session.status = "pending_preview"
        logger.info(f"{doc_type.upper()} 檔案已存 GCS 路徑，跳過向量化", extra=log_extra)
        return

    if is_skip_file(doc_type):
        document.status = "skipped"
        session.status = "pending_preview"
        logger.info(f"{doc_type} 檔案 v1 不處理，存 GCS 保留", extra=log_extra)
        return

    file_bytes = await gcs_service.download_bytes(document.gcs_raw_path)

    if doc_type == "docx":
        structured = parse_docx(file_bytes)
        await _run_gemini_text_and_save(
            structured=structured,
            session=session,
            document=document,
            company_context=company_context,
            db=db,
            log_extra=log_extra,
        )
        return

    if doc_type == "pdf":
        logger.info("PDF 直送 Gemini Flash 視覺理解", extra=log_extra)
        await _run_gemini_pdf_and_save(
            file_bytes=file_bytes,
            session=session,
            document=document,
            company_context=company_context,
            db=db,
            log_extra=log_extra,
        )
        return

    logger.warning(f"未知 doc_type: {doc_type}，跳過", extra=log_extra)
    document.status = "skipped"
    session.status = "pending_preview"


async def _run_gemini_pdf_and_save(
    file_bytes: bytes,
    session: IngestionSession,
    document: Document,
    company_context: dict,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    session_id = str(session.session_id)
    doc_id = str(document.doc_id)
    company_id_str = str(session.company_id)

    result: PdfConversionResult = await convert_pdf_to_chunks(
        file_bytes=file_bytes,
        session_id=session_id,
        doc_id=doc_id,
        company_context=company_context,
    )

    document.has_low_confidence = result.has_quality_issue
    document.min_confidence = None
    document.status = "gemini_processed"

    if result.has_quality_issue and result.quality_note:
        quality_gcs_path = settings.gcs_processed_path(company_id_str, session_id)
        await gcs_service.upload_json(
            quality_gcs_path,
            {"has_quality_issue": True, "quality_note": result.quality_note},
        )

    await _save_chunks_to_db(
        chunk_outputs=result.chunks,
        session=session,
        document=document,
        company_context=company_context,
        db=db,
        log_extra=log_extra,
    )


async def _run_gemini_text_and_save(
    structured: dict,
    session: IngestionSession,
    document: Document,
    company_context: dict,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    session_id = str(session.session_id)
    doc_id = str(document.doc_id)

    chunk_outputs = await convert_to_chunks(
        structured_text=structured,
        session_id=session_id,
        doc_id=doc_id,
        company_context=company_context,
    )

    document.has_low_confidence = None
    document.min_confidence = None
    document.status = "gemini_processed"

    await _save_chunks_to_db(
        chunk_outputs=chunk_outputs,
        session=session,
        document=document,
        company_context=company_context,
        db=db,
        log_extra=log_extra,
    )


async def _save_chunks_to_db(
    chunk_outputs: list,
    session: IngestionSession,
    document: Document,
    company_context: dict,
    db: AsyncSession,
    log_extra: dict,
) -> None:
    """
    chunks 存 GCS converted/ + 寫 Cloud SQL。

    Phase 3 變更：rule_version 從 company_context 取。
    Phase 4 變更：新增 face 欄位。
    """
    company_id_uuid: uuid.UUID = session.company_id
    company_id_str = str(company_id_uuid)
    session_id = str(session.session_id)

    # 存 converted/ GCS（永久保留）
    converted_gcs_path = settings.gcs_converted_path(company_id_str, session_id)
    await gcs_service.upload_json(
        converted_gcs_path,
        [c.model_dump() for c in chunk_outputs],
    )

    # rule_version 從 company_context 取（Phase 3 核心接縫點）
    rule_version = company_context["rule_version"]
    session.rule_version_used = rule_version

    for idx, chunk_output in enumerate(chunk_outputs):
        chunk = Chunk(
            doc_id=document.doc_id,
            company_id=company_id_uuid,
            chunk_index=idx,
            rule_version=rule_version,
            doc_type=document.doc_type,
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
            face=chunk_output.face,           # Phase 4 新增
            code_gcs_path=None,
            drawing_gcs_path=None,
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
