
"""
app/models/session.py

ingestion_sessions 資料表。狀態機是整個系統的骨幹。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 狀態機（§10-1）
SESSION_STATUSES = (
    "pending_preview",  # 上傳完成，等待 OCR + Gemini
    "confirmed",        # 管理員 Mirror View 確認
    "processing",       # 批次寫入 Cloud SQL + Qdrant（Phase 4）
    "done",             # 知識可被查詢
    "failed",           # 處理失敗，可重試
)


class IngestionSession(Base):
    __tablename__ = "ingestion_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        Enum(*SESSION_STATUSES, name="session_status_enum"),
        nullable=False,
        default="pending_preview",
    )
    fail_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    preview_confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)
    rule_version_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

