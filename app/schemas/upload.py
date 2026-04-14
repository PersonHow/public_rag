"""
app/schemas/upload.py

Upload endpoint 的 request/response schema。
⚠ company_id 不在任何 request schema 中，永遠從 config 取（Phase 2 改為 JWT）。
"""
import uuid
from pydantic import BaseModel


class UploadResponse(BaseModel):
    session_id: uuid.UUID
    doc_id: uuid.UUID
    status: str
    doc_type: str
    gcs_raw_path: str


class SessionStatusResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    fail_reason: str | None = None
    preview_confirmed: bool


class ConfirmResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    message: str
