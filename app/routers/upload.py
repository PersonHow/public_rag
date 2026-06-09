"""
app/routers/upload.py

POST /upload — 接收 multipart/form-data，上傳至 GCS，建立 DB 記錄，以 BackgroundTask 處理文件。

權限（v2 變更）：
  - 僅 superadmin 可上傳（company_admin / field_user 皆 403）
  - superadmin 須帶 ?company_id=XXX 指定目標公司
"""
import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, get_session_factory
from app.core.logging import get_logger
from app.core.dependencies import require_roles, require_company_id
from app.models.document import Document
from app.models.session import IngestionSession
from app.schemas.upload import UploadResponse
from app.schemas.auth import CurrentUser
from app.services.document.detector import detect_doc_type_from_filename

router = APIRouter(tags=["upload"])
settings = get_settings()
logger = get_logger("upload")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

_upload_allowed = require_roles("superadmin")


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File(description="上傳文件（PDF / DOCX / TAP / NC / DXF）")],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(_upload_allowed),
    company_id: uuid.UUID = Depends(require_company_id),
) -> UploadResponse:
    """
    文件上傳 Endpoint。

    處理流程：
    1. 副檔名輕量偵測 doc_type
    2. 上傳至 GCS raw/{company_id}/{session_id}/{doc_id}/{filename}
    3. 建立 ingestion_sessions 記錄
    4. 建立 documents 記錄（含 gcs_raw_path）
    5. 以 FastAPI BackgroundTask 在同一 container 內異步處理文件
    6. 回傳 { session_id, doc_id, status }
    """
    company_id_str = str(company_id)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"檔案超過 {MAX_FILE_SIZE // 1024 // 1024}MB 限制")

    filename = file.filename or "unknown"
    doc_type = detect_doc_type_from_filename(filename)

    session_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    gcs_path = settings.gcs_raw_path(company_id_str, str(session_id), str(doc_id), filename)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: _upload_sync(gcs_path, file_bytes, file.content_type or "application/octet-stream"),
        )
    except Exception as e:
        logger.error(f"GCS 上傳失敗: {e}", extra={"session_id": str(session_id), "doc_id": str(doc_id)})
        raise HTTPException(status_code=500, detail="GCS 上傳失敗")

    session = IngestionSession(
        session_id=session_id,
        company_id=company_id,      # uuid.UUID
        status="pending_preview",
        preview_confirmed=False,
    )
    db.add(session)
    await db.flush()

    document = Document(
        doc_id=doc_id,
        company_id=company_id,      # uuid.UUID
        session_id=session_id,
        filename=filename,
        doc_type=doc_type,
        gcs_raw_path=gcs_path,
        status="uploaded",
    )
    db.add(document)
    await db.flush()

    # 先 commit 再派發 Cloud Tasks：避免 worker 在本交易 commit 前就查不到 session/document
    # （worker 找不到 row 會回 200 → Cloud Tasks 不重試 → 文件靜默遺失）
    await db.commit()

    await _enqueue_with_fallback(
        str(session_id), str(doc_id), doc_type, company_id_str, background_tasks,
    )

    logger.info(
        "文件上傳完成",
        extra={
            "session_id": str(session_id),
            "doc_id": str(doc_id),
            "filename": filename,
            "doc_type": doc_type,
            "company_id": company_id_str,
            "uploaded_by": str(current_user.user_id),
        },
    )

    return UploadResponse(
        session_id=session_id,
        doc_id=doc_id,
        status="pending_preview",
        doc_type=doc_type,
        gcs_raw_path=gcs_path,
    )


async def _enqueue_with_fallback(
    session_id_str: str,
    doc_id_str: str,
    doc_type: str,
    company_id_str: str,
    background_tasks: BackgroundTasks,
    max_retries: int = 3,
) -> None:
    """
    先嘗試 Cloud Tasks 最多 max_retries 次；全部失敗才改用 BackgroundTask。
    enqueue_process_document 是同步 blocking call，用 run_in_executor 包裝。
    """
    from app.services.storage.tasks import enqueue_process_document

    session_id = uuid.UUID(session_id_str)
    doc_id = uuid.UUID(doc_id_str)
    loop = asyncio.get_event_loop()
    log_extra = {"session_id": session_id_str, "doc_id": doc_id_str}

    logger.info(
        "Cloud Tasks 排程開始",
        extra={
            **log_extra,
            "doc_type":     doc_type,
            "company_id":   company_id_str,
            "queue":        settings.CLOUD_TASKS_QUEUE,
            "worker_url":   f"{settings.WORKER_BASE_URL}/internal/tasks/process-document",
            "max_retries":  max_retries,
        },
    )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        logger.info(
            f"Cloud Tasks 嘗試中（第 {attempt}/{max_retries} 次）",
            extra={
                **log_extra,
                "attempt":    attempt,
                "doc_type":   doc_type,
                "company_id": company_id_str,
            },
        )
        try:
            task_name = await loop.run_in_executor(
                None,
                lambda: enqueue_process_document(session_id, doc_id, doc_type, company_id_str),
            )
            logger.info(
                f"Cloud Tasks 排程成功（第 {attempt}/{max_retries} 次）",
                extra={**log_extra, "task_name": task_name},
            )
            return
        except Exception as e:
            last_error = e
            logger.warning(
                f"Cloud Tasks 排程失敗（第 {attempt}/{max_retries} 次）: {type(e).__name__}: {e}",
                extra={**log_extra, "attempt": attempt, "error": str(e)},
            )
            if attempt < max_retries:
                await asyncio.sleep(0.5)

    logger.error(
        f"Cloud Tasks {max_retries} 次全部失敗，改用 BackgroundTask",
        extra={**log_extra, "final_error": str(last_error)},
    )
    background_tasks.add_task(
        _process_document_background,
        session_id_str, doc_id_str, doc_type, company_id_str,
    )


async def _process_document_background(
    session_id_str: str,
    doc_id_str: str,
    doc_type: str,
    company_id_str: str,
) -> None:
    """BackgroundTask fallback：Cloud Tasks 未設定或失敗時，在同一 container 內處理文件。"""
    from app.routers.internal.tasks import (
        _build_company_context,
        _route_document,
        _mark_session_failed,
    )
    from app.services.ai.gemini import GeminiMaxRetriesError

    session_id = uuid.UUID(session_id_str)
    doc_id = uuid.UUID(doc_id_str)
    log_extra = {"session_id": session_id_str, "doc_id": doc_id_str, "via": "background_task"}

    async with get_session_factory()() as db:
        try:
            session_result = await db.execute(
                select(IngestionSession).where(IngestionSession.session_id == session_id)
            )
            session = session_result.scalar_one_or_none()
            doc_result = await db.execute(
                select(Document).where(Document.doc_id == doc_id)
            )
            document = doc_result.scalar_one_or_none()

            if not session or not document:
                logger.error("BackgroundTask: session/document 不存在", extra=log_extra)
                return

            company_context = await _build_company_context(db, session.company_id)
            await _route_document(session, document, doc_type, company_context, db, log_extra)
            await db.commit()

        except GeminiMaxRetriesError as e:
            await db.rollback()
            async with get_session_factory()() as db2:
                s2 = (await db2.execute(
                    select(IngestionSession).where(IngestionSession.session_id == session_id)
                )).scalar_one_or_none()
                if s2:
                    await _mark_session_failed(s2, db2, reason=str(e), log_extra=log_extra)
                    await db2.commit()

        except Exception as e:
            logger.error(f"BackgroundTask 未預期錯誤: {e}", extra=log_extra)
            await db.rollback()
            async with get_session_factory()() as db2:
                s2 = (await db2.execute(
                    select(IngestionSession).where(IngestionSession.session_id == session_id)
                )).scalar_one_or_none()
                if s2:
                    await _mark_session_failed(s2, db2, reason=f"background_task: {e}", log_extra=log_extra)
                    await db2.commit()


def _upload_sync(gcs_path: str, data: bytes, content_type: str) -> None:
    from google.cloud import storage
    client = storage.Client(project=settings.GCS_PROJECT)
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(data, content_type=content_type)


def _get_routing_description(doc_type: str) -> str:
    routes = {
        "pdf": "Gemini Flash 直讀（視覺理解）",
        "docx": "python-docx 直接解析",
        "tap": "存 GCS 路徑，不進向量庫",
        "nc": "存 GCS 路徑，不進向量庫",
        "dxf": "v1 存 GCS 保留，不處理",
        "unknown": "未知類型，存 GCS 保留",
    }
    return routes.get(doc_type, "未知路由")
