"""
app/routers/companies.py

POST   /companies                        — 建立公司（superadmin only）
GET    /companies                        — 列出所有公司（含各自的 session 數）
GET    /companies/{company_id}           — 公司詳情
PUT    /companies/{company_id}           — 修改公司名稱／產業／負責人聯絡資訊
PATCH  /companies/{company_id}/deactivate — 停用公司
"""
import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.models.company import Company
from app.models.session import IngestionSession
from app.schemas.auth import CurrentUser
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies", tags=["companies"])

_superadmin_only = require_roles("superadmin")


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    body: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(_superadmin_only),
):
    company = Company(company_id=uuid.uuid4(), is_active=True, **body.model_dump())
    db.add(company)
    await db.commit()
    await db.refresh(company)
    logger.info({"level": "INFO", "phase": "phase2", "service": "companies",
                 "session_id": None, "company_id": str(company.company_id),
                 "message": f"Company created: {company.name}"})
    return company


@router.get("", response_model=List[CompanyResponse])
async def list_companies(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(_superadmin_only),
):
    session_count = (
        select(IngestionSession.company_id, func.count().label("n"))
        .group_by(IngestionSession.company_id)
        .subquery()
    )
    result = await db.execute(
        select(Company, func.coalesce(session_count.c.n, 0))
        .outerjoin(session_count, session_count.c.company_id == Company.company_id)
        .order_by(Company.name)
    )
    return [
        CompanyResponse.model_validate(company).model_copy(update={"session_count": n})
        for company, n in result.all()
    ]


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(_superadmin_only),
):
    result = await db.execute(select(Company).where(Company.company_id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(_superadmin_only),
):
    result = await db.execute(select(Company).where(Company.company_id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    for field, value in body.model_dump().items():
        setattr(company, field, value)
    await db.commit()
    await db.refresh(company)
    logger.info({"level": "INFO", "phase": "phase2", "service": "companies",
                 "session_id": None, "company_id": str(company_id),
                 "message": f"Company updated: {company.name}"})
    return company


@router.patch("/{company_id}/deactivate", response_model=CompanyResponse)
async def deactivate_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(_superadmin_only),
):
    result = await db.execute(select(Company).where(Company.company_id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.is_active = False
    await db.commit()
    await db.refresh(company)
    logger.info({"level": "INFO", "phase": "phase2", "service": "companies",
                 "session_id": None, "company_id": str(company_id),
                 "message": "Company deactivated"})
    return company
