"""
tests/test_auth_cookie.py

整合測試：驗證 access_token 改走 httpOnly cookie 的完整流程。
- 真實 router（/auth/login、/auth/logout）+ 真實 get_current_user + 真實 JWT 簽發/解析
- 假 DB / 假 user（不連遠端正式庫）
涵蓋：登入寫 cookie 且 body 不外洩 token、帶 cookie 可通過驗證、缺 cookie 回 401、登出清 cookie。
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.routers import auth as auth_router
from app.schemas.auth import CurrentUser, TokenResponse
from app.services.auth import create_access_token


def _make_user():
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        email="alice@example.com",
        role="company_admin",
        company_id=uuid.uuid4(),
        is_active=True,
    )


def _build_client(db_user):
    app = FastAPI()
    app.include_router(auth_router.router)

    @app.get("/whoami")
    async def whoami(user: CurrentUser = Depends(get_current_user)):
        return {"email": user.email, "role": user.role}

    async def _fake_db():
        result = SimpleNamespace(scalar_one_or_none=lambda: db_user)
        yield SimpleNamespace(execute=AsyncMock(return_value=result))

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_login_sets_httponly_cookie_and_hides_token_in_body():
    user = _make_user()
    client = _build_client(user)
    token = create_access_token(user)

    fake_login = AsyncMock(return_value=TokenResponse(
        access_token=token, role=user.role,
        company_id=str(user.company_id), company_name="Acme",
    ))
    with patch.object(auth_router.auth_service, "login", fake_login):
        resp = client.post("/auth/login", json={"email": user.email, "password": "x"})

    assert resp.status_code == 200
    # body 只有身分資訊，token 不外洩給 JS
    assert "access_token" not in resp.json()
    assert resp.json()["role"] == user.role
    # cookie 確實寫入且為 HttpOnly
    assert "access_token" in resp.cookies
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_cookie_authenticates_protected_route():
    user = _make_user()
    client = _build_client(user)
    token = create_access_token(user)

    fake_login = AsyncMock(return_value=TokenResponse(
        access_token=token, role=user.role,
        company_id=str(user.company_id), company_name="Acme",
    ))
    with patch.object(auth_router.auth_service, "login", fake_login):
        client.post("/auth/login", json={"email": user.email, "password": "x"})

    # TestClient 會保留 cookie；後續請求不帶 Authorization header 也能通過
    resp = client.get("/whoami")
    assert resp.status_code == 200
    assert resp.json()["email"] == user.email


def test_missing_cookie_returns_401():
    user = _make_user()
    client = _build_client(user)
    resp = client.get("/whoami")  # 沒登入、沒 cookie、沒 header
    assert resp.status_code == 401


def test_logout_clears_cookie():
    user = _make_user()
    client = _build_client(user)
    token = create_access_token(user)

    fake_login = AsyncMock(return_value=TokenResponse(
        access_token=token, role=user.role,
        company_id=str(user.company_id), company_name="Acme",
    ))
    with patch.object(auth_router.auth_service, "login", fake_login):
        client.post("/auth/login", json={"email": user.email, "password": "x"})

    assert client.get("/whoami").status_code == 200  # 登入後可存取

    logout = client.post("/auth/logout")
    assert logout.status_code == 204

    # 登出後 cookie 已清除 → 受保護路由回 401
    client.cookies.clear()
    assert client.get("/whoami").status_code == 401
