"""
app/routers/health.py

GET /health — DB 連線狀態
GET /ready  — GCS + Vertex AI 連線
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.gcs import check_gcs_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
    }


@router.get("/ready")
async def ready() -> dict:
    gcs_ok = await check_gcs_connection()
    # Vertex AI 連線在 TokenManager 初始化時驗證，這裡只做 GCS
    return {
        "status": "ok" if gcs_ok else "degraded",
        "gcs": "connected" if gcs_ok else "disconnected",
    }
