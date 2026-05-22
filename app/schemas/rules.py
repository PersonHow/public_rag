"""
app/schemas/rules.py

company_rules CRUD 的 request/response schema。
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

# chunks 表允許的目標欄位（術語對照驗證用）
_VALID_CHUNK_FIELDS = {
    "product_name", "product_id", "material", "dimensions", "specs",
    "situation", "action", "reason", "applies_to", "case_id", "doc_type",
}


class CompanyRulesCreate(BaseModel):
    """POST /companies/{company_id}/rules 的 request body。"""
    terminology_mapping: dict[str, str] = {}
    doc_type_hints: list[str] = []
    field_exclusions: list[str] = []
    extra_instructions: list[str] = []

    @field_validator("terminology_mapping")
    @classmethod
    def validate_terminology_mapping(cls, v: dict[str, str]) -> dict[str, str]:
        """確保每個術語對照的目標是有效的 chunks 欄位。"""
        for term, field in v.items():
            if field not in _VALID_CHUNK_FIELDS:
                raise ValueError(
                    f"術語「{term}」的對照目標「{field}」不是有效的 chunks 欄位。"
                    f"可用欄位：{sorted(_VALID_CHUNK_FIELDS)}"
                )
        return v


class CompanyRulesResponse(BaseModel):
    """GET /companies/{company_id}/rules 的 response。"""
    rule_id: uuid.UUID
    company_id: uuid.UUID
    field_mapping: dict
    rule_version: str
    created_at: datetime

    class Config:
        from_attributes = True


class CompanyRulesHistoryItem(BaseModel):
    """GET /companies/{company_id}/rules/history 的單筆項目（不回傳 field_mapping 內容）。"""
    rule_id: uuid.UUID
    rule_version: str
    created_at: datetime

    class Config:
        from_attributes = True
