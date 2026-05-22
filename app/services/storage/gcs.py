"""
app/services/gcs.py

GCS 操作：上傳、下載、JSON 讀寫。
所有路徑由 config.py 的方法生成，不在此處拼接路徑。
"""
import asyncio
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


async def download_bytes(gcs_path: str, timeout_sec: int = 30) -> bytes:
    bucket = _get_bucket()
    blob = bucket.blob(gcs_path)
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, blob.download_as_bytes),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"GCS 下載逾時（{timeout_sec}s）: {gcs_path}")


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

"""
 
generate_signed_url()：Phase 5 查詢時給 field_user 下載 .TAP 用。
簽名需要 Service Account credentials（ADC 不支援 sign_bytes）。
本機開發若 ADC 無法簽名，會拋出 google.auth.exceptions.TransportError，
query router 已有 try/except 處理，code_download_url 回傳 null。
"""
 
def generate_signed_url(gcs_path: str, expiration_seconds: int = 3600) -> str:
    """
    生成 GCS 物件的簽名 URL，讓 field_user 直接下載（不需要 GCS 帳號）。
    有效期預設 1 小時。
 
    注意：需要 Service Account credentials 才能 sign。
    Cloud Run 環境：Compute Engine default service account 支援 sign。
    本機開發：需要 service account JSON（GOOGLE_APPLICATION_CREDENTIALS）。
    如果用 gcloud auth application-default login 的 user credentials 則不支援 sign，
    此時 query router 的 try/except 會捕捉並回傳 code_download_url=null。
    """
    import datetime
    client = _get_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(gcs_path)
    url = blob.generate_signed_url(
        expiration=datetime.timedelta(seconds=expiration_seconds),
        method="GET",
        version="v4",
    )
    return url
