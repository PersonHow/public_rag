"""
app/routers/rules.py

GET  /companies/{company_id}/rules         — 取最新版本 rules
POST /companies/{company_id}/rules         — 建立新版本（INSERT only，舊版本保留）
GET  /companies/{company_id}/rules/history — 歷史版本清單（metadata only）

權限：
  superadmin    → 讀寫任意公司
  company_admin → 讀寫自家公司
  field_user    → 無權限
"""
import uuid
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.company import Company
from app.schemas.auth import CurrentUser
from app.schemas.rules import CompanyRulesCreate, CompanyRulesResponse, CompanyRulesHistoryItem
from app.services import rules as rules_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rules"])


def _check_company_access(current_user: CurrentUser, company_id: uuid.UUID) -> None:
    """
    確認目前登入者有權限操作該公司的 rules。
    field_user 完全無權；company_admin 只能操作自家公司。
    """
    if current_user.role == "field_user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if current_user.role == "company_admin" and current_user.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access another company's rules")


@router.get("/companies/{company_id}/rules", response_model=CompanyRulesResponse)
async def get_latest_rules(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """取得該公司最新版本的 rules。尚未設定時回傳 404。"""
    _check_company_access(current_user, company_id)

    rule = await rules_service.get_latest_rules(db, company_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"公司 {company_id} 尚未設定 rules，上傳文件時將使用通用預設 prompt。",
        )
    return rule


@router.post(
    "/companies/{company_id}/rules",
    response_model=CompanyRulesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rules(
    company_id: uuid.UUID,
    body: CompanyRulesCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    建立新版本 rules（INSERT，舊版本永不刪除）。
    每次呼叫都會產生一個新 rule_version，供 chunks 追溯用。
    """
    _check_company_access(current_user, company_id)

    # 確認公司存在
    company_result = await db.execute(select(Company).where(Company.company_id == company_id))
    if not company_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    field_mapping = {
        "terminology_mapping": body.terminology_mapping,
        "doc_type_hints": body.doc_type_hints,
        "field_exclusions": body.field_exclusions,
        "extra_instructions": body.extra_instructions,
    }

    rule = await rules_service.create_rules(db, company_id, field_mapping)

    logger.info({
        "level": "INFO",
        "phase": "phase3",
        "service": "rules",
        "session_id": None,
        "company_id": str(company_id),
        "message": f"company_rules 更新",
        "rule_version": rule.rule_version,
        "updated_by": str(current_user.user_id),
    })

    return rule


@router.get("/companies/{company_id}/rules/history", response_model=List[CompanyRulesHistoryItem])
async def get_rules_history(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """歷史版本清單（只回傳 rule_id、rule_version、created_at，不回傳 field_mapping）。"""
    _check_company_access(current_user, company_id)

    history = await rules_service.get_rules_history(db, company_id)
    return history
