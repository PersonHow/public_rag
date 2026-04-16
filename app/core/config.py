"""
app/core/config.py

所有環境變數與常數集中定義。
⚠ DEFAULT_COMPANY_ID 是唯一合法的 company_id 來源（Phase 1）。
   Phase 2 改為從 JWT token 取值，此檔案不需要改動 schema。

架構調整說明：
  Document AI 相關設定全數移除。
  所有 PDF 直接送 Gemini Flash 視覺理解，不再走 OCR pipeline。
  min_confidence 欄位不再使用（has_low_confidence 語意改為 Gemini quality flag）。
"""
from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────
    app_env: str = "development"

    # Phase 1 固定值。Phase 2 改為從 JWT token 取，不改此定義。
    DEFAULT_COMPANY_ID: str = "dev-company"

    # Cloud Tasks worker 驗證用
    INTERNAL_TOKEN: str = "dev-internal-token-change-in-prod"

    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/rag_db"
    DB_POOL_SIZE_MIN: int = 5
    DB_POOL_SIZE_MAX: int = 20
    DB_POOL_TIMEOUT: int = 30

    # ── GCS ──────────────────────────────────────────────
    GCS_BUCKET_NAME: str = "your-rag-bucket"
    GCS_PROJECT: str=""

    # ── Cloud Tasks ──────────────────────────────────────
    CLOUD_TASKS_PROJECT: str = ""
    CLOUD_TASKS_LOCATION: str = "asia-east1"
    CLOUD_TASKS_QUEUE: str = "rag-ingestion"
    CLOUD_TASKS_MAX_RETRIES: int = 3
    WORKER_BASE_URL: str = "http://localhost:8000"
    
    # ── JWT ────────────────────────────────────── 
    JWT_SECRET_KEY: str = "public_rag_phase_2_secret_jwt_key_for_once_again"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # ── Vertex AI / Gemini ───────────────────────────────
    VERTEX_AI_PROJECT: str = ""
    VERTEX_AI_LOCATION: str = "us-central1"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_MAX_RETRIES: int = 3
    GEMINI_PDF_TIMEOUT_SEC:int = 120

    # ── GCS 路徑規則（唯一定義處）────────────────────────
    # raw/  → 含 doc_id 層防止同名覆蓋
    # processed/ → 15 天後自動刪除（Gemini quality report 存這裡）
    # converted/ → Gemini 輸出，永久保留
    @property
    def gcs_raw_prefix(self) -> str:
        return "raw"

    @property
    def gcs_processed_prefix(self) -> str:
        return "processed"

    @property
    def gcs_converted_prefix(self) -> str:
        return "converted"

    def gcs_raw_path(self, company_id: str, session_id: str, doc_id: str, filename: str) -> str:
        """raw/{company_id}/{session_id}/{doc_id}/{filename}"""
        return f"raw/{company_id}/{session_id}/{doc_id}/{filename}"

    def gcs_processed_path(self, company_id: str, session_id: str) -> str:
        """processed/{company_id}/{session_id}/quality_report.json"""
        return f"processed/{company_id}/{session_id}/quality_report.json"

    def gcs_structured_path(self, company_id: str, session_id: str) -> str:
        """processed/{company_id}/{session_id}/structured.json"""
        return f"processed/{company_id}/{session_id}/structured.json"

    def gcs_converted_path(self, company_id: str, session_id: str) -> str:
        """converted/{company_id}/{session_id}/chunks.json"""
        return f"converted/{company_id}/{session_id}/chunks.json"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
