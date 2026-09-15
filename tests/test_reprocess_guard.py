"""
tests/test_reprocess_guard.py

POST /sessions/{id}/reprocess 守衛邏輯測試。
用 dependency override 注入 mock DB + superadmin，驗證守衛分支，不連真實 DB / Qdrant。

涵蓋：
  - 進行中狀態（confirmed / processing）→ 409，且不派送任何 task
  - 沒有 document → 400
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_db
from app.routers import sessions
from app.schemas.auth import CurrentUser

_SUPERADMIN = CurrentUser(
    user_id=uuid.uuid4(),
    email="admin@test.com",
    role="superadmin",
    company_id=uuid.uuid4(),
)


def _result_with_session(session):
    """模擬 _get_session_or_404 用的 execute 結果（scalar_one_or_none）。"""
    r = MagicMock()
    r.scalar_one_or_none.return_value = session
    return r


def _result_with_docs(docs):
    """模擬 documents 查詢結果（scalars().all()）。"""
    r = MagicMock()
    r.scalars.return_value.all.return_value = docs
    return r


def _make_db(execute_results):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_results)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _override_with(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[sessions._confirm_allowed] = lambda: _SUPERADMIN


async def _post_reprocess(session_id: uuid.UUID):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.post(f"/sessions/{session_id}/reprocess")


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize("status", ["confirmed", "processing"])
async def test_in_flight_status_rejected(status):
    sid = uuid.uuid4()
    session = SimpleNamespace(session_id=sid, company_id=uuid.uuid4(), status=status)
    db = _make_db([_result_with_session(session)])
    _override_with(db)

    resp = await _post_reprocess(sid)

    assert resp.status_code == 409
    # 守衛應在查 documents / 派送前就擋下：execute 只被呼叫一次（session 查詢）
    assert db.execute.await_count == 1
    db.commit.assert_not_awaited()


async def test_no_documents_rejected():
    sid = uuid.uuid4()
    session = SimpleNamespace(session_id=sid, company_id=uuid.uuid4(), status="done")
    db = _make_db([_result_with_session(session), _result_with_docs([])])
    _override_with(db)

    resp = await _post_reprocess(sid)

    assert resp.status_code == 400
    db.commit.assert_not_awaited()
