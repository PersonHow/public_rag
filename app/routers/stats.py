"""
app/routers/stats.py

GET /dashboard/stats — Hub 首頁統計數字

回傳：
  pending_count    — 待確認 session 數（status = pending_preview）
  processing_count — 處理中 session 數（status in confirmed / processing）
  doc_count        — 知識庫 chunk 數（done session 的 chunks）
  member_count     — 公司成員數（field_user / company_admin；admin 才回傳，否則 null）

company_id 永遠從 JWT 取；superadmin 可帶 ?company_id= 指定目標公司。
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.chunk import Chunk
from app.models.session import IngestionSession
from app.models.user import User
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    pending_count: int
    processing_count: int
    doc_count: int
    member_count: Optional[int] = None  # field_user 不回傳


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    company_id: Optional[uuid.UUID] = Query(default=None),  # superadmin 專用
) -> DashboardStats:

    # ── 決定 effective_company_id ─────────────────────────────────────────
    if current_user.role == "superadmin":
        if company_id:
            effective_company_id = company_id
        else:
            # superadmin 未指定 → 全平台統計
            effective_company_id = None
    else:
        effective_company_id = current_user.company_id

    # ── 1. 待確認（pending_preview）──────────────────────────────────────
    pending_q = select(func.count()).select_from(IngestionSession).where(
        IngestionSession.status == "pending_preview"
    )
    if effective_company_id:
        pending_q = pending_q.where(IngestionSession.company_id == effective_company_id)
    pending_count = (await db.execute(pending_q)).scalar_one()

    # ── 2. 處理中（confirmed / processing）───────────────────────────────
    processing_q = select(func.count()).select_from(IngestionSession).where(
        IngestionSession.status.in_(["confirmed", "processing"])
    )
    if effective_company_id:
        processing_q = processing_q.where(IngestionSession.company_id == effective_company_id)
    processing_count = (await db.execute(processing_q)).scalar_one()

    # ── 3. 知識庫 chunk 數（done session 的 chunks）───────────────────────
    doc_q = select(func.count()).select_from(Chunk)
    if effective_company_id:
        doc_q = doc_q.where(Chunk.company_id == effective_company_id)
    doc_count = (await db.execute(doc_q)).scalar_one()

    # ── 4. 成員數（admin 才回傳）─────────────────────────────────────────
    member_count: Optional[int] = None
    if current_user.role in ("superadmin", "company_admin"):
        member_q = select(func.count()).select_from(User).where(User.is_active == True)
        if effective_company_id:
            member_q = member_q.where(User.company_id == effective_company_id)
        member_count = (await db.execute(member_q)).scalar_one()

    return DashboardStats(
        pending_count=pending_count,
        processing_count=processing_count,
        doc_count=doc_count,
        member_count=member_count,
    )
