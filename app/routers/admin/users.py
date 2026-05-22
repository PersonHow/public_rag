"""
app/routers/users.py

POST  /users                      — 建立用戶
GET   /users/me                   — 取自己的資料
GET   /users                      — 列出用戶（自動 company_id filter）
PATCH /users/{user_id}/deactivate — 停用用戶
"""
import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.company import Company
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.schemas.user import UserCreate, UserResponse
from app.services.auth import hash_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # field_user 無建立權限
    if current_user.role == "field_user":
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # company_admin 只能建立自家的 field_user
    if current_user.role == "company_admin":
        if body.role != "field_user":
            raise HTTPException(status_code=403, detail="company_admin can only create field_user")
        if body.company_id and body.company_id != current_user.company_id:
            raise HTTPException(status_code=403, detail="Cannot create user for another company")
        body.company_id = current_user.company_id

    # superadmin 建立非 superadmin 時必須指定 company_id
    if current_user.role == "superadmin" and body.role != "superadmin" and not body.company_id:
        raise HTTPException(status_code=400, detail="company_id required for non-superadmin users")

    # email 唯一性檢查
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    # 驗證 company_id 存在
    if body.company_id:
        company_result = await db.execute(
            select(Company).where(Company.company_id == body.company_id)
        )
        if not company_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Company not found")

    user = User(
        user_id=uuid.uuid4(),
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        company_id=body.company_id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info({"level": "INFO", "phase": "phase2", "service": "users",
                 "session_id": None,
                 "company_id": str(user.company_id) if user.company_id else None,
                 "message": f"User created: {user.email}", "role": user.role})
    return user


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.user_id == current_user.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role == "field_user":
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    query = select(User)
    if current_user.role == "company_admin":
        query = query.where(User.company_id == current_user.company_id)

    result = await db.execute(query.order_by(User.email))
    return result.scalars().all()


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role == "field_user":
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role == "company_admin" and user.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Cannot deactivate user from another company")

    user.is_active = False
    await db.commit()
    await db.refresh(user)
    logger.info({"level": "INFO", "phase": "phase2", "service": "users",
                 "session_id": None,
                 "company_id": str(user.company_id) if user.company_id else None,
                 "message": f"User deactivated: {user.email}"})
    return user
