"""
app/routers/auth.py

POST /auth/login   → 驗證帳密，access_token 寫入 httpOnly cookie
POST /auth/logout  → 清除 cookie

登入/登出行為皆寫入 login_logs 稽核紀錄（含來源 IP 與 User-Agent），
DB 寫入在 services/auth.py，此處負責取得 client 資訊與 stdout log。
"""
import logging
import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse
from app.services import auth as auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

COOKIE_NAME = "access_token"


def _client_info(request: Request) -> Tuple[Optional[str], Optional[str]]:
    """取得來源 IP 與 User-Agent。

    Cloud Run 前有 proxy，客戶端 IP 取 X-Forwarded-For 第一段；
    本機直連則 fallback 到 request.client.host。

    注意：這個值不可信。Cloud Run 是把實際連線位址「附加」在請求端送來的
    X-Forwarded-For 之後，所以第一段是對方自己填的，實測可任意偽造。
    login_logs.ip 因此只能當參考，不能當稽核依據；登入節流也不可只綁 IP
    （見 services/auth.py 的 LOGIN_FAIL_MAX_PER_EMAIL）。
    要讓這個值可信，必須先讓後端不能被直接連線。
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    if user_agent:
        user_agent = user_agent[:500]
    return ip, user_agent


def _set_auth_cookie(response: Response, token: str) -> None:
    # 不設 max_age → session cookie：瀏覽器完全關閉即失效。
    # JWT 本身的 exp（JWT_EXPIRE_HOURS）仍是後端的絕對有效期限。
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    ip, user_agent = _client_info(request)
    try:
        result = await auth_service.login(
            db, body.email, body.password, ip=ip, user_agent=user_agent
        )
    except auth_service.LoginRateLimited as exc:
        logger.warning({"level": "WARNING", "phase": "phase2", "service": "auth",
                        "session_id": None, "company_id": None,
                        "message": "Login blocked: too many failed attempts",
                        "email": body.email, "reason": "rate_limited", "ip": ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    except PermissionError:
        logger.warning({"level": "WARNING", "phase": "phase2", "service": "auth",
                        "session_id": None, "company_id": None,
                        "message": "Login failed: account inactive",
                        "email": body.email, "reason": "account_inactive", "ip": ip})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    if not result:
        logger.warning({"level": "WARNING", "phase": "phase2", "service": "auth",
                        "session_id": None, "company_id": None,
                        "message": "Login failed: invalid credentials",
                        "email": body.email, "reason": "invalid_credentials", "ip": ip})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    logger.info({"level": "INFO", "phase": "phase2", "service": "auth",
                 "session_id": None, "company_id": result.company_id,
                 "message": "Login success",
                 "user_id": result.user_id, "email": result.email,
                 "role": result.role, "ip": ip})

    _set_auth_cookie(response, result.access_token)
    return LoginResponse(
        role=result.role,
        company_id=result.company_id,
        company_name=result.company_name,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # 軟性解析 cookie：token 有效就記錄登出者身分；無效或缺 token 仍允許清 cookie。
    token = request.cookies.get(COOKIE_NAME)
    payload = auth_service.decode_token(token) if token else None
    if payload and payload.get("sub") and payload.get("email"):
        ip, user_agent = _client_info(request)
        company_id = payload.get("company_id")
        await auth_service.record_login_event(
            db,
            event="logout",
            email=payload["email"],
            user_id=uuid.UUID(payload["sub"]),
            company_id=uuid.UUID(company_id) if company_id else None,
            ip=ip,
            user_agent=user_agent,
        )
        logger.info({"level": "INFO", "phase": "phase2", "service": "auth",
                     "session_id": None, "company_id": company_id,
                     "message": "Logout",
                     "user_id": payload["sub"], "email": payload["email"], "ip": ip})
    response.delete_cookie(key=COOKIE_NAME, path="/")
