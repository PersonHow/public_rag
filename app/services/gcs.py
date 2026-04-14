"""
app/services/gcs.py

GCS 操作：上傳、下載、JSON 讀寫。
所有路徑由 config.py 的方法生成，不在此處拼接路徑。
"""
import json
from typing import Any

from google.cloud import storage

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("gcs")


def _get_client() -> storage.Client:
    return storage.Client(project=settings.GCS_PROJECT)


def _get_bucket() -> storage.Bucket:
    return _get_client().bucket(settings.GCS_BUCKET_NAME)


async def upload_file_bytes(gcs_path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    上傳 bytes 到 GCS，回傳 gs:// URI。
    注意：google-cloud-storage 是同步 SDK，在 Worker（背景 task）中呼叫。
    若需要 FastAPI endpoint 中非同步上傳，用 run_in_executor 包裝。
    """
    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(data, content_type=content_type)
    gcs_uri = f"gs://{settings.GCS_BUCKET_NAME}/{gcs_path}"
    logger.debug(f"GCS upload 完成: {gcs_uri}")
    return gcs_uri


async def upload_file_from_path(gcs_path: str, local_path: str, content_type: str = "application/octet-stream") -> str:
    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path, content_type=content_type)
    return f"gs://{settings.GCS_BUCKET_NAME}/{gcs_path}"


async def download_bytes(gcs_path: str) -> bytes:
    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    return blob.download_as_bytes()


async def upload_json(gcs_path: str, data: Any) -> str:
    """序列化 JSON 後上傳，確保 UTF-8 + ensure_ascii=False（繁中支援）。"""
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return await upload_file_bytes(gcs_path, payload, content_type="application/json")


async def download_json(gcs_path: str) -> Any:
    raw = await download_bytes(gcs_path)
    return json.loads(raw.decode("utf-8"))


def get_gcs_uri(gcs_path: str) -> str:
    return f"gs://{settings.GCS_BUCKET_NAME}/{gcs_path}"


async def check_gcs_connection() -> bool:
    """readiness check 用。"""
    try:
        bucket = _get_bucket()
        bucket.reload()
        return True
    except Exception as e:
        logger.error(f"GCS 連線失敗: {e}")
        return False
