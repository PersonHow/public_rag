"""
app/models/conversation.py

conversation_history 資料表。
每次 /query 問答各存一列（單表查詢歷史，無多輪會話分組、不帶上下文）。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 使用者刪除時保留歷史（審計用）
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    # 只存 doc_filename / chunk_context / score；signed URL 會過期，不存
    sources: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_conversation_history_company_created", "company_id", "created_at"),
        Index("ix_conversation_history_user_created", "user_id", "created_at"),
    )
