"""
app/models/chunk.py

chunks 資料表，20 欄位（Phase 4 新增 face）。
Phase 2：company_id 從 String(100) 改為 UUID（刻意無 FK，denormalized，查詢免 JOIN）。
Phase 4：新增 face VARCHAR(100) nullable，加工面向原始術語。
embed_text 是唯一用於向量化的欄位，NOT NULL 強制。
code_gcs_path / drawing_gcs_path 由 pipeline 後處理注入（Phase 4 inject-gcs-paths）。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Index, String, Text, func
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

    # ── Phase 4 新增：加工面向（Nullable）────────────────
    # 原始文件術語，不 normalize（第一面 / 第二面 / 面A / OP10 等）
    # 保留各公司術語多租戶彈性，TAP 路徑注入時轉換為檔名後綴
    face: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # ── Phase 5 新增：chunk 排序索引（Nullable，向後相容）────────────────
    chunk_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── 附件（Nullable，後處理注入）──────────────────────
    code_gcs_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    drawing_gcs_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        # inject-gcs-paths 查詢：WHERE company_id=? AND product_id IS NOT NULL AND code_gcs_path IS NULL
        Index("ix_chunks_company_code_path", "company_id", "code_gcs_path"),
        Index("ix_chunks_doc_id_chunk_index", "doc_id", "chunk_index"),
        # product_id 比對查詢加速
        Index("ix_chunks_company_product_id", "company_id", "product_id"),
    )
