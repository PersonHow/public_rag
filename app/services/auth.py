"""
app/services/auth.py

bcrypt 密碼驗證、JWT 簽發/解析、login() 流程。
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.models.user import User
from app.schemas.auth import TokenResponse, CurrentUser

settings = get_settings()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.user_id),
        "email": user.email,
        "role": user.role,
        "company_id": str(user.company_id) if user.company_id else None,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def login(db: AsyncSession, email: str, password: str) -> Optional[TokenResponse]:
    user = await authenticate_user(db, email, password)
    if not user:
        return None
    if not user.is_active:
        raise PermissionError("account_inactive")
    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        role=user.role,
        company_id=str(user.company_id) if user.company_id else None,
    )
