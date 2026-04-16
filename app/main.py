"""
app/main.py

FastAPI 應用入口。
所有 router 在此掛載，logging 在 startup 設定。
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.routers import health, sessions, tasks, upload
from app.routers import auth, companies, users, internal_setup  # Phase 2 Add

settings = get_settings()

# JSON structured logging
setup_logging(level=logging.DEBUG if settings.app_env == "development" else logging.INFO)

app = FastAPI(
    title="多租戶 RAG 生產助理系統",
    description="Phase 2 — 多租戶基礎",
    version="2.0.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else ["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(sessions.router)
app.include_router(tasks.router)

# Phase 2
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(users.router)
app.include_router(internal_setup.router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "RAG Production Assistant",
        "phase": "Phase 2 — 多租戶基礎",
    }
