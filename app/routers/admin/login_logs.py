"""
app/routers/admin/login_logs.py

GET /login-logs — 查詢登入稽核紀錄（供合規稽核／異常追查）
  - superadmin：全部，可用 ?company_id= 過濾
  - company_admin：僅自家公司
  - field_user：403
篩選：email（部分比對）、event、start/end 時間區間；limit/offset 分頁。
"""
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.login_log import LoginLog, LOGIN_EVENTS
from app.schemas.auth import CurrentUser
from app.schemas.login_log import LoginLogListResponse

router = APIRouter(prefix="/login-logs", tags=["login-logs"])


@router.get("", response_model=LoginLogListResponse)
async def list_login_logs(
    email: Optional[str] = Query(default=None),
    event: Optional[str] = Query(default=None),
    company_id: Optional[uuid.UUID] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role == "field_user":
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if event and event not in LOGIN_EVENTS:
        raise HTTPException(status_code=400, detail=f"event must be one of {LOGIN_EVENTS}")

    query = select(LoginLog)
    if current_user.role == "company_admin":
        query = query.where(LoginLog.company_id == current_user.company_id)
    elif company_id:
        query = query.where(LoginLog.company_id == company_id)

    if email:
        query = query.where(LoginLog.email.ilike(f"%{email}%"))
    if event:
        query = query.where(LoginLog.event == event)
    if start:
        query = query.where(LoginLog.created_at >= start)
    if end:
        query = query.where(LoginLog.created_at <= end)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(LoginLog.created_at.desc()).limit(limit).offset(offset)
    )
    return LoginLogListResponse(total=total, items=result.scalars().all())
