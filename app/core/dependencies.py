"""
app/core/dependencies.py

FastAPI dependency：
  - get_current_user       → JWT 驗證，回傳 CurrentUser
  - require_roles(*roles)  → RBAC 工廠，回傳只允許指定 role 的 dependency
  - resolve_company_id     → superadmin 用 ?company_id=，其他從 JWT 取
  - require_company_id     → 同上，但強制不能為 None
"""
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.services.auth import decode_token

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.user_id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    company_id_raw = payload.get("company_id")
    return CurrentUser(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        company_id=uuid.UUID(company_id_raw) if company_id_raw else None,
    )


def require_roles(*roles: str):
    """RBAC 工廠：回傳只允許指定 role 的 dependency。"""
    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return _check


def resolve_company_id(
    current_user: CurrentUser = Depends(get_current_user),
    company_id: Optional[uuid.UUID] = Query(default=None),
) -> Optional[uuid.UUID]:
    """
    company_id 解析規則：
    - field_user / company_admin → 從 JWT 取，忽略 query param
    - superadmin → 優先用 ?company_id=XXX，未帶則 None
    """
    if current_user.role == "superadmin":
        return company_id
    return current_user.company_id


def require_company_id(
    resolved: Optional[uuid.UUID] = Depends(resolve_company_id),
    current_user: CurrentUser = Depends(get_current_user),
) -> uuid.UUID:
    """resolve_company_id 的強制版本，None 時拋 400。"""
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="superadmin must provide ?company_id= for this operation",
        )
    return resolved
