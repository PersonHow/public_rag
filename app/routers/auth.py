"""
app/routers/auth.py

POST /auth/login
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import auth as auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
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
    return result
