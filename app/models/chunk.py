"""
app/models/chunk.py

chunks 資料表，19 欄位。
Phase 2：company_id 從 String(100) 改為 UUID（刻意無 FK，denormalized，查詢免 JOIN）。
embed_text 是唯一用於向量化的欄位，NOT NULL 強制。
code_gcs_path / drawing_gcs_path 由 pipeline 後處理注入（Phase 4）。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    # ── 系統欄位（NOT NULL）──────────────────────────────
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Phase 2：String(100) → UUID，刻意無 FK（denormalized，查詢免 JOIN）
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    embed_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 規格組（Nullable）────────────────────────────────
    product_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    product_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    dimensions: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    specs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── 知識組（Nullable）────────────────────────────────
    situation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applies_to: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── 通用（Nullable）──────────────────────────────────
    case_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── 附件（Nullable，後處理注入）──────────────────────
    code_gcs_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    drawing_gcs_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
