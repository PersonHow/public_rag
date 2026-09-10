"""
app/main.py

FastAPI 應用入口。
所有 router 在此掛載，logging 在 startup 設定。

Phase 5 變更：
  - version 5.0.0
  - 掛載 query router
"""
import logging
import secrets

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    # 只關 docs_url/redoc_url 不夠：openapi_url 保持預設時 schema 仍然公開，
    # 等於把全部端點（含 /internal/init-superadmin）的路徑與參數格式送給對方。
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
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


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """資安弱掃修復：純 API 服務不載入任何資源，CSP 鎖到最嚴。
    /docs、/redoc（僅非 production 存在）需要載入 Swagger UI 資源，故排除。"""
    response = await call_next(request)
    is_docs = request.url.path.startswith(("/docs", "/redoc", "/openapi.json"))
    if settings.app_env == "production" or not is_docs:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["X-Frame-Options"] = "DENY"
    return response


# 不經由前端 proxy、因此不能要求共享密鑰的路徑：
#   /internal/  Cloud Tasks 直接打 WORKER_BASE_URL，另有 X-Internal-Token 把關
#   /health /ready  Cloud Run 與監控探測
_PROXY_GUARD_EXEMPT = ("/internal/", "/health", "/ready")


@app.middleware("http")
async def proxy_guard_middleware(request, call_next):
    """確認請求出自前端 nginx，擋掉繞過前端直接打後端網址的呼叫。

    後端 ingress 仍是 all，這是應用層補丁而非網路層根治：
    密鑰存在前端容器的環境變數裡，能讀到該容器的人就能偽造。
    要真正根治得讓後端不可被公網直連（Direct VPC egress）。

    定義位置在 security_headers_middleware 之後 —— Starlette 後加的疊在最外層，
    所以擋下的請求不會進到後續任何處理。
    回 404 而非 403：不讓對方用狀態碼確認端點存在。
    """
    if settings.PROXY_SHARED_SECRET and not request.url.path.startswith(_PROXY_GUARD_EXEMPT):
        supplied = request.headers.get("X-Proxy-Auth", "")
        if not secrets.compare_digest(supplied.encode(), settings.PROXY_SHARED_SECRET.encode()):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)


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
