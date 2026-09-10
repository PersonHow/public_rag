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
from sqlalchemy import select, func

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


# 帳號不存在時拿來墊檔的 hash。rounds 與 hash_password 相同（皆為 gensalt 預設），
# 確保「查無此人」與「密碼錯誤」兩條路徑耗時一致。
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"never-matches", bcrypt.gensalt()).decode()

# 登入失敗節流，兩層門檻：
#   email + IP  5 次 / 15 分鐘 —— 擋單機爆破，不波及同帳號的其他來源
#   email      20 次 / 15 分鐘 —— 擋輪換 IP 的爆破
# 之所以不能只靠 IP：Cloud Run 的 X-Forwarded-For 第一段是請求端自己送來的值，
# 實測可任意偽造（見 _client_info），攻擊者每次換一個假 IP 就繞過。
# email 是攻擊目標本身、無從迴避，所以它才是底線；IP 那層只是讓正常爆破更早被攔下。
LOGIN_FAIL_WINDOW = timedelta(minutes=15)
LOGIN_FAIL_MAX_PER_IP = 5
LOGIN_FAIL_MAX_PER_EMAIL = 20


class LoginRateLimited(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds


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
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def _retry_after_seconds(oldest: datetime) -> int:
    """時間窗內最早那次失敗滾出視窗，還要多久。"""
    remaining = (oldest + LOGIN_FAIL_WINDOW) - datetime.now(timezone.utc)
    return max(int(remaining.total_seconds()), 1)


async def _recent_login_failures(db: AsyncSession, email: str, ip: Optional[str]):
    """回傳 (email 失敗數, 最早時間, email+IP 失敗數, 最早時間)。

    單次查詢走 ix_login_logs_email_created 索引（email, created_at），
    IP 那組以 FILTER 在同一次掃描內算出，不需要第二趟。
    """
    since = datetime.now(timezone.utc) - LOGIN_FAIL_WINDOW
    result = await db.execute(
        select(
            func.count(),
            func.min(LoginLog.created_at),
            func.count().filter(LoginLog.ip == ip),
            func.min(LoginLog.created_at).filter(LoginLog.ip == ip),
        ).where(
            LoginLog.event == "login_failed",
            LoginLog.email == email,
            LoginLog.created_at >= since,
        )
    )
    return result.one()


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
    # 節流檢查放在 authenticate_user 之前：被擋下的請求不必付 bcrypt 的成本。
    email_fails, email_oldest, ip_fails, ip_oldest = await _recent_login_failures(db, email, ip)
    if ip_fails >= LOGIN_FAIL_MAX_PER_IP:
        raise LoginRateLimited(_retry_after_seconds(ip_oldest))
    if email_fails >= LOGIN_FAIL_MAX_PER_EMAIL:
        raise LoginRateLimited(_retry_after_seconds(email_oldest))

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
