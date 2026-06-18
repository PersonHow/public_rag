"""
app/routers/auth.py

POST /auth/login   → 驗證帳密，access_token 寫入 httpOnly cookie
POST /auth/logout  → 清除 cookie
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.auth import LoginRequest, LoginResponse
from app.services import auth as auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

COOKIE_NAME = "access_token"


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.JWT_EXPIRE_HOURS * 3600,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        result = await auth_service.login(db, body.email, body.password)
    except PermissionError:
        logger.warning({"level": "WARNING", "phase": "phase2", "service": "auth",
                        "session_id": None, "company_id": None,
                        "message": "Login failed: account inactive",
                        "email": body.email, "reason": "account_inactive"})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    if not result:
        logger.warning({"level": "WARNING", "phase": "phase2", "service": "auth",
                        "session_id": None, "company_id": None,
                        "message": "Login failed: invalid credentials",
                        "email": body.email, "reason": "invalid_credentials"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    logger.info({"level": "INFO", "phase": "phase2", "service": "auth",
                 "session_id": None, "company_id": result.company_id,
                 "message": "Login success", "role": result.role})

    _set_auth_cookie(response, result.access_token)
    return LoginResponse(
        role=result.role,
        company_id=result.company_id,
        company_name=result.company_name,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
