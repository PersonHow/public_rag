"""
app/models/company_rule.py

company_rules 資料表。
Phase 2 建表，Phase 3 實作 CRUD。
舊版本不刪除，每次更新 rules 新增一筆記錄，chunk 的 rule_version 供追溯。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyRule(Base):
    __tablename__ = "company_rules"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.company_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 完整 rules 結構：terminology_mapping / doc_type_hints / field_exclusions / extra_instructions
    field_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 格式：v1-YYMMDD-HHMM
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
