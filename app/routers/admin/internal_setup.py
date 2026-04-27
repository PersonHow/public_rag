"""
app/routers/init.py

POST /internal/init-superadmin

一次性端點，建立第一個 superadmin。
X-Internal-Token 驗證（與 process-document 共用同一個 token）。
superadmin 已存在（相同 email）時回傳 400，天生幂等不需要額外關閉。
"""
import uuid
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import get_settings
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.auth import hash_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])
settings = get_settings()


@router.post("/init-superadmin", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def init_superadmin(
    body: UserCreate,
    x_internal_token: str = Header(..., alias="X-Internal-Token"),
    db: AsyncSession = Depends(get_db),
):
    if x_internal_token != settings.INTERNAL_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")

    if body.role != "superadmin":
        raise HTTPException(status_code=400, detail="This endpoint only creates superadmin accounts")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        user_id=uuid.uuid4(),
        email=body.email,
        password_hash=hash_password(body.password),
        role="superadmin",
        company_id=None,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info({"level": "INFO", "phase": "phase2", "service": "init",
                 "session_id": None, "company_id": None,
                 "message": f"Superadmin created: {user.email}",
                 "user_id": str(user.user_id)})
    return user
