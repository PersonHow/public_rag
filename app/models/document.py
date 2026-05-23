
"""
app/models/document.py

documents 資料表。
含更新版新增欄位：gcs_raw_path（含 doc_id 層）、min_confidence、has_low_confidence。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # 更新版決策 2：Worker 直接查 DB 取路徑，不重建路徑字串
    gcs_raw_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")

    # OCR confidence（掃描 PDF 才有值，其他填 null）
    min_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    has_low_confidence: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
