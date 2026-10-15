"""
tests/test_company_update.py

PUT /companies/{id}：superadmin 修改租戶名稱／產業／負責人聯絡資訊。
GET /companies：列表附帶各租戶的 session 數。
用 dependency override 注入 mock DB + superadmin，不連真實 DB。
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_db
from app.routers.admin import companies
from app.schemas.auth import CurrentUser

_SUPERADMIN = CurrentUser(
    user_id=uuid.uuid4(),
    email="admin@test.com",
    role="superadmin",
    company_id=uuid.uuid4(),
)


def _company(**overrides):
    fields = dict(
        company_id=uuid.uuid4(), name="Acme", industry=None,
        contact_name=None, contact_phone=None, contact_email=None,
        is_active=True, created_at=datetime.now(timezone.utc),
    )
    return SimpleNamespace(**(fields | overrides))


def _make_db(company):
    result = MagicMock()
    result.scalar_one_or_none.return_value = company
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _override_with(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[companies._superadmin_only] = lambda: _SUPERADMIN


async def _put(company_id: uuid.UUID, body: dict):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.put(f"/companies/{company_id}", json=body)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


async def test_update_name_and_industry():
    company = _company(name="Old", industry="錯的產業")
    cid = company.company_id
    db = _make_db(company)
    _override_with(db)

    resp = await _put(cid, {"name": "New", "industry": "閥門製造"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "New"
    assert resp.json()["industry"] == "閥門製造"
    assert (company.name, company.industry) == ("New", "閥門製造")
    db.commit.assert_awaited_once()


async def test_clear_industry():
    company = _company(industry="錯的產業")
    cid = company.company_id
    _override_with(_make_db(company))

    resp = await _put(cid, {"name": "Acme", "industry": None})

    assert resp.status_code == 200
    assert company.industry is None


async def test_not_found():
    db = _make_db(None)
    _override_with(db)

    resp = await _put(uuid.uuid4(), {"name": "X"})

    assert resp.status_code == 404
    db.commit.assert_not_awaited()


async def test_update_contact():
    company = _company()
    _override_with(_make_db(company))

    resp = await _put(company.company_id, {
        "name": "Acme", "contact_name": "王小明",
        "contact_phone": "02-1234-5678", "contact_email": "wang@acme.com",
    })

    assert resp.status_code == 200
    assert resp.json()["contact_email"] == "wang@acme.com"
    assert (company.contact_name, company.contact_phone) == ("王小明", "02-1234-5678")


async def test_invalid_contact_email_rejected():
    company = _company()
    db = _make_db(company)
    _override_with(db)

    resp = await _put(company.company_id, {"name": "Acme", "contact_email": "not-an-email"})

    assert resp.status_code == 422
    db.commit.assert_not_awaited()


async def test_list_includes_session_count():
    with_sessions, without_sessions = _company(name="A"), _company(name="B")
    result = MagicMock()
    result.all.return_value = [(with_sessions, 3), (without_sessions, 0)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    _override_with(db)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/companies")

    assert resp.status_code == 200
    assert [c["session_count"] for c in resp.json()] == [3, 0]
