"""
app/models/login_log.py

login_logs 資料表：登入行為稽核紀錄（audit log）。
event 值：login_success / login_failed / account_inactive / logout。
email 直接落地（非只存 FK），確保使用者被刪除後稽核紀錄仍可追溯。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

LOGIN_EVENTS = ("login_success", "login_failed", "account_inactive", "logout")


class LoginLog(Base):
    __tablename__ = "login_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(300), nullable=False)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.company_id", ondelete="SET NULL"),
        nullable=True,
    )
    event: Mapped[str] = mapped_column(String(30), nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
