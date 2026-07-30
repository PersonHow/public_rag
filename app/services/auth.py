"""
app/services/auth.py

bcrypt 密碼驗證、JWT 簽發/解析、login() 流程、登入稽核紀錄（login_logs）。
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
from app.models.company import Company
from app.models.login_log import LoginLog
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


async def record_login_event(
    db: AsyncSession,
    *,
    event: str,
    email: str,
    user_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """寫入 login_logs 稽核紀錄。

    立即 commit：登入失敗的 request 最後會 raise HTTPException，
    若不在此 commit，get_db 會 rollback 導致稽核紀錄遺失。
    """
    db.add(LoginLog(
        log_id=uuid.uuid4(),
        user_id=user_id,
        email=email,
        company_id=company_id,
        event=event,
        ip=ip,
        user_agent=user_agent,
    ))
    await db.commit()


async def login(
    db: AsyncSession,
    email: str,
    password: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[TokenResponse]:
    user = await authenticate_user(db, email, password)
    if not user:
        await record_login_event(
            db, event="login_failed", email=email, ip=ip, user_agent=user_agent
        )
        return None
    if not user.is_active:
        await record_login_event(
            db, event="account_inactive", email=email,
            user_id=user.user_id, company_id=user.company_id,
            ip=ip, user_agent=user_agent,
        )
        raise PermissionError("account_inactive")

    company_name: Optional[str] = None
    if user.company_id:
        result = await db.execute(select(Company).where(Company.company_id == user.company_id))
        company = result.scalar_one_or_none()
        if company:
            company_name = company.name

    user.last_login_at = datetime.now(timezone.utc)
    await record_login_event(
        db, event="login_success", email=email,
        user_id=user.user_id, company_id=user.company_id,
        ip=ip, user_agent=user_agent,
    )

    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        user_id=str(user.user_id),
        email=user.email,
        role=user.role,
        company_id=str(user.company_id) if user.company_id else None,
        company_name=company_name,
    )
