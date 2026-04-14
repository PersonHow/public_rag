"""
app/routers/upload.py

POST /upload — 接收 multipart/form-data，上傳至 GCS，建立 DB 記錄，派送 Cloud Tasks。

⚠ company_id 不在任何 request 參數中，統一從 settings.DEFAULT_COMPANY_ID 取得。
   Phase 2 改為從 JWT token 取，此 router 只需換一行取值來源。
"""
import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.document import Document
from app.models.session import IngestionSession
from app.schemas.upload import UploadResponse
from app.services import gcs as gcs_service
from app.services import tasks as tasks_service
from app.services.detector import detect_doc_type_from_filename

router = APIRouter(tags=["upload"])
settings = get_settings()
logger = get_logger("upload")

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File(description="上傳文件（PDF / DOCX / TAP / NC / DXF）")],
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """
    文件上傳 Endpoint（§5）。

    處理流程：
    1. 副檔名輕量偵測 doc_type
    2. 上傳至 GCS raw/{company_id}/{session_id}/{doc_id}/{filename}
    3. 建立 ingestion_sessions 記錄
    4. 建立 documents 記錄（含 gcs_raw_path）
    5. 派送 Cloud Tasks（最大重試 3 次）
    6. 回傳 { session_id, doc_id, status }
    """
    # ── Phase 2 接縫點：此處改為 current_user.company_id ──────────────
    company_id = settings.DEFAULT_COMPANY_ID

    # 讀取檔案
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"檔案超過 {MAX_FILE_SIZE // 1024 // 1024}MB 限制")

    filename = file.filename or "unknown"

    # 1. 副檔名輕量偵測
    doc_type = detect_doc_type_from_filename(filename)

    # 2. 生成 ID
    session_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    # 3. GCS 路徑（含 doc_id 層，防止同名覆蓋）
    gcs_path = settings.gcs_raw_path(company_id, str(session_id), str(doc_id), filename)

    # 4. 上傳至 GCS（在背景線程執行，避免 blocking event loop）
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: _upload_sync(gcs_path, file_bytes, file.content_type or "application/octet-stream"),
        )
    except Exception as e:
        logger.error(f"GCS 上傳失敗: {e}", extra={"session_id": str(session_id), "doc_id": str(doc_id)})
        raise HTTPException(status_code=500, detail="GCS 上傳失敗")

    # 5. 建立 ingestion_sessions
    session = IngestionSession(
        session_id=session_id,
        company_id=company_id,
        status="pending_preview",
        preview_confirmed=False,
    )
    db.add(session)
    await db.flush()

    # 6. 建立 documents（gcs_raw_path 必填）
    document = Document(
        doc_id=doc_id,
        company_id=company_id,
        session_id=session_id,
        filename=filename,
        doc_type=doc_type,
        gcs_raw_path=gcs_path,
        status="uploaded",
    )
    db.add(document)
    await db.flush()  # 取得 DB ID 後再派 task

    # 7. 派送 Cloud Tasks
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: tasks_service.enqueue_process_document(
                session_id=session_id,
                doc_id=doc_id,
                doc_type=doc_type,
                company_id=company_id,
            ),
        )
    except Exception as e:
        # Cloud Tasks 派送失敗不影響 upload 成功，但記錄 ERROR
        logger.error(
            f"Cloud Tasks 派送失敗（可手動觸發）: {e}",
            extra={"session_id": str(session_id), "doc_id": str(doc_id)},
        )

    logger.info(
        "文件上傳完成",
        extra={
            "session_id": str(session_id),
            "doc_id": str(doc_id),
            "filename": filename,
            "doc_type": doc_type,
        },
    )
    logger.info(
        "文件類型偵測結果",
        extra={
            "doc_id": str(doc_id),
            "detected_type": doc_type,
            "routing": _get_routing_description(doc_type),
        },
    )

    return UploadResponse(
        session_id=session_id,
        doc_id=doc_id,
        status="pending_preview",
        doc_type=doc_type,
        gcs_raw_path=gcs_path,
    )


def _upload_sync(gcs_path: str, data: bytes, content_type: str) -> None:
    """同步 GCS 上傳（在 executor 中執行）。"""
    from google.cloud import storage
    client = storage.Client(project=settings.GCS_PROJECT)
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(data, content_type=content_type)


def _get_routing_description(doc_type: str) -> str:
    routes = {
        "pdf": "Worker 內部精確分流（pdfplumber 試讀）",
        "docx": "python-docx 直接解析",
        "tap": "存 GCS 路徑，不進向量庫",
        "nc": "存 GCS 路徑，不進向量庫",
        "dxf": "v1 存 GCS 保留，不處理",
        "unknown": "未知類型，存 GCS 保留",
    }
    return routes.get(doc_type, "未知路由")
