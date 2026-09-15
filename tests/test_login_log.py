"""
tests/test_login_log.py

登入稽核紀錄（login_logs）測試：
- 登入失敗 / 帳號停用 / 登入成功皆寫入對應 event 的稽核紀錄（且立即 commit）
- 登入成功更新 users.last_login_at
- 登出（帶有效 cookie）寫入 logout 紀錄
- _client_info 的 X-Forwarded-For / fallback 解析
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.login_log import LoginLog
from app.routers import auth as auth_router
from app.routers.auth import _client_info
from app.services import auth as auth_service


class FakeDb:
    """模擬 AsyncSession：execute 依序回傳 results，add/commit 供稽核寫入。"""

    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.commit = AsyncMock()

    async def execute(self, *_args, **_kwargs):
        value = self._results.pop(0)
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    def add(self, obj):
        self.added.append(obj)


def _make_user(*, is_active=True):
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        email="alice@example.com",
        password_hash=auth_service.hash_password("correct-pw"),
        role="superadmin",
        company_id=None,
        is_active=is_active,
        last_login_at=None,
    )


def _audit_logs(db):
    return [obj for obj in db.added if isinstance(obj, LoginLog)]


@pytest.mark.asyncio
async def test_login_failed_records_audit():
    db = FakeDb([None])  # 查無此 email
    result = await auth_service.login(db, "ghost@example.com", "x", ip="1.2.3.4", user_agent="ua")

    assert result is None
    logs = _audit_logs(db)
    assert len(logs) == 1
    assert logs[0].event == "login_failed"
    assert logs[0].email == "ghost@example.com"
    assert logs[0].user_id is None
    assert logs[0].ip == "1.2.3.4"
    # 失敗路徑後續會 raise HTTPException，必須已 commit 否則稽核紀錄被 rollback
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_login_wrong_password_records_audit():
    user = _make_user()
    db = FakeDb([user])
    result = await auth_service.login(db, user.email, "wrong-pw")

    assert result is None
    logs = _audit_logs(db)
    assert len(logs) == 1
    assert logs[0].event == "login_failed"
    assert logs[0].email == user.email


@pytest.mark.asyncio
async def test_login_inactive_records_audit():
    user = _make_user(is_active=False)
    db = FakeDb([user])

    with pytest.raises(PermissionError):
        await auth_service.login(db, user.email, "correct-pw", ip="1.2.3.4")

    logs = _audit_logs(db)
    assert len(logs) == 1
    assert logs[0].event == "account_inactive"
    assert logs[0].user_id == user.user_id
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_login_success_records_audit_and_last_login():
    user = _make_user()
    db = FakeDb([user])
    result = await auth_service.login(db, user.email, "correct-pw", ip="1.2.3.4", user_agent="ua")

    assert result is not None
    assert result.user_id == str(user.user_id)
    assert result.email == user.email
    assert user.last_login_at is not None

    logs = _audit_logs(db)
    assert len(logs) == 1
    assert logs[0].event == "login_success"
    assert logs[0].user_id == user.user_id
    assert logs[0].ip == "1.2.3.4"
    assert logs[0].user_agent == "ua"


def test_logout_with_valid_cookie_records_audit():
    user = _make_user()
    token = auth_service.create_access_token(user)
    db = FakeDb([])

    app = FastAPI()
    app.include_router(auth_router.router)

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)
    client.cookies.set("access_token", token)

    resp = client.post("/auth/logout")
    assert resp.status_code == 204

    logs = _audit_logs(db)
    assert len(logs) == 1
    assert logs[0].event == "logout"
    assert logs[0].user_id == user.user_id
    assert logs[0].email == user.email


def test_logout_without_cookie_records_nothing():
    db = FakeDb([])
    app = FastAPI()
    app.include_router(auth_router.router)

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    client = TestClient(app)

    resp = client.post("/auth/logout")
    assert resp.status_code == 204
    assert _audit_logs(db) == []


def test_client_info_prefers_x_forwarded_for():
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1", "user-agent": "TestUA"},
        client=SimpleNamespace(host="10.0.0.99"),
    )
    ip, user_agent = _client_info(request)
    assert ip == "203.0.113.7"
    assert user_agent == "TestUA"


def test_client_info_fallback_to_client_host():
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="192.168.1.10"))
    ip, user_agent = _client_info(request)
    assert ip == "192.168.1.10"
    assert user_agent is None
