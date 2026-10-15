"""
tests/test_user_list.py

GET /users：列表附帶各使用者所屬租戶名稱（superadmin 無租戶 → null）。
company_admin 只能看到自家使用者。
用 dependency override 注入 mock DB + 登入者，不連真實 DB。
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.auth import CurrentUser


def _user(email: str, role: str, company_id=None):
    return SimpleNamespace(
        user_id=uuid.uuid4(), email=email, role=role, company_id=company_id,
        is_active=True, last_login_at=None,
    )


def _override_with(rows, current_user: CurrentUser) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return db


async def _get_users():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.get("/users")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


async def test_list_includes_company_name():
    company_id = uuid.uuid4()
    superadmin = CurrentUser(user_id=uuid.uuid4(), email="root@test.com", role="superadmin", company_id=None)
    _override_with([
        (_user("root@test.com", "superadmin"), None),
        (_user("boss@acme.com", "company_admin", company_id), "Acme"),
    ], superadmin)

    resp = await _get_users()

    assert resp.status_code == 200
    assert [(u["email"], u["company_name"]) for u in resp.json()] == [
        ("root@test.com", None),
        ("boss@acme.com", "Acme"),
    ]


async def test_company_admin_query_filtered_by_own_company():
    company_id = uuid.uuid4()
    company_admin = CurrentUser(user_id=uuid.uuid4(), email="boss@acme.com", role="company_admin", company_id=company_id)
    db = _override_with([], company_admin)

    await _get_users()

    query = db.execute.await_args.args[0]
    assert list(query.compile().params.values()) == [company_id]


async def test_field_user_forbidden():
    field_user = CurrentUser(user_id=uuid.uuid4(), email="w@acme.com", role="field_user", company_id=uuid.uuid4())
    db = _override_with([], field_user)

    resp = await _get_users()

    assert resp.status_code == 403
    db.execute.assert_not_awaited()
