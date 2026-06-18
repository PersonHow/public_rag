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

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.services.auth import decode_token

# auto_error=False：缺 Authorization header 時回傳 None 而非直接 403，
# 讓我們能 fallback 到 httpOnly cookie。
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    # 優先用 httpOnly cookie（瀏覽器），其次 Authorization: Bearer（非瀏覽器用戶端／測試）。
    token = request.cookies.get("access_token") if request is not None else None
    if not token and credentials is not None:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

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

    # role 與 company_id 一律取 DB 即時值，而非 JWT 簽發時的快照：
    # 使用者被改公司／改角色／停用後，舊 token 到期前不會再存取到舊資料。
    # （此處本就已查 DB，故不增加額外查詢成本。）
    return CurrentUser(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        company_id=user.company_id,
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
