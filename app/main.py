"""
app/main.py

FastAPI 應用入口。
所有 router 在此掛載，logging 在 startup 設定。

Phase 5 變更：
  - version 5.0.0
  - 掛載 query router
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.routers import health, sessions, upload
from app.routers import auth, rules                             # Phase 2 / Phase 3
from app.routers import query, preview, stats                          # Phase 5
from app.routers import conversations                                   # Phase 6
from app.routers.internal import tasks
from app.routers.admin import companies, users, internal_setup, login_logs  # Phase 2

settings = get_settings()

setup_logging(level=logging.DEBUG if settings.app_env == "development" else logging.INFO)

app = FastAPI(
    title="多租戶 RAG 生產助理系統",
    description="Phase 5 — RAG 查詢",
    version="5.0.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

_cors_origins = ["*"] if settings.app_env == "development" else [
    o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup Event ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event() -> None:
    """
    Phase 4：確保 Qdrant collection 存在。
    冪等：已存在跳過，不報錯。
    Production 環境：初始化失敗直接 raise，讓 Cloud Run 拒絕啟動。
    """
    startup_logger = logging.getLogger("startup")
    startup_logger.info(f"CORS_ORIGINS: {_cors_origins}")
    try:
        from app.services.ai.qdrant_service import init_collection
        init_collection()
        startup_logger.info("Qdrant collection 初始化完成")
    except Exception as e:
        if settings.app_env == "production":
            startup_logger.error(f"Qdrant 初始化失敗，production 環境拒絕啟動: {e}")
            raise
        startup_logger.warning(f"Qdrant 初始化失敗（本機開發可忽略）: {e}")


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(sessions.router)
app.include_router(tasks.router)

# Phase 2
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(users.router)
app.include_router(internal_setup.router)
app.include_router(login_logs.router)

# Phase 3
app.include_router(rules.router)

# Phase 5
app.include_router(query.router)
app.include_router(preview.router)
app.include_router(stats.router)

# Phase 6
app.include_router(conversations.router)

@app.get("/")
async def root() -> dict:
    return {
        "service": "RAG Production Assistant",
        "phase": "Phase 5 — RAG 查詢",
    }
