"""
tests/test_get_current_user.py

#5 回歸測試：get_current_user 的 role / company_id 一律取 DB 即時值，
而非 JWT 簽發時的快照。避免使用者被改公司／改角色後，舊 token 仍存取舊資料。
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core import dependencies
from app.core.dependencies import get_current_user


def _make_db_returning(user):
    """模擬 AsyncSession：db.execute(...) → result.scalar_one_or_none() == user。"""
    result = SimpleNamespace(scalar_one_or_none=lambda: user)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    return db


def _make_user(*, company_id, role="field_user", is_active=True):
    return SimpleNamespace(
        user_id=uuid.uuid4(),
        email="u@example.com",
        role=role,
        company_id=company_id,
        is_active=is_active,
    )


@pytest.mark.asyncio
async def test_company_id_comes_from_db_not_token():
    """token 帶舊公司，DB 已改新公司 → 回傳新公司。"""
    db_company = uuid.uuid4()
    stale_token_company = uuid.uuid4()
    user = _make_user(company_id=db_company)
    db = _make_db_returning(user)
    creds = SimpleNamespace(credentials="fake-token")

    with patch.object(
        dependencies, "decode_token",
        return_value={"sub": str(user.user_id), "company_id": str(stale_token_company)},
    ):
        current = await get_current_user(credentials=creds, db=db)

    assert current.company_id == db_company
    assert current.company_id != stale_token_company


@pytest.mark.asyncio
async def test_role_comes_from_db_not_token():
    """token 帶舊角色，DB 已降級 → 回傳 DB 角色。"""
    user = _make_user(company_id=uuid.uuid4(), role="field_user")
    db = _make_db_returning(user)
    creds = SimpleNamespace(credentials="fake-token")

    with patch.object(
        dependencies, "decode_token",
        return_value={"sub": str(user.user_id), "role": "company_admin", "company_id": str(user.company_id)},
    ):
        current = await get_current_user(credentials=creds, db=db)

    assert current.role == "field_user"


@pytest.mark.asyncio
async def test_superadmin_db_company_id_none():
    """superadmin 在 DB 的 company_id 為 None → 回傳 None（即使 token 曾帶值）。"""
    user = _make_user(company_id=None, role="superadmin")
    db = _make_db_returning(user)
    creds = SimpleNamespace(credentials="fake-token")

    with patch.object(
        dependencies, "decode_token",
        return_value={"sub": str(user.user_id), "company_id": str(uuid.uuid4())},
    ):
        current = await get_current_user(credentials=creds, db=db)

    assert current.company_id is None
    assert current.role == "superadmin"


@pytest.mark.asyncio
async def test_inactive_user_rejected():
    """DB 上 is_active=False → 401（即使 token 仍有效）。"""
    from fastapi import HTTPException

    user = _make_user(company_id=uuid.uuid4(), is_active=False)
    db = _make_db_returning(user)
    creds = SimpleNamespace(credentials="fake-token")

    with patch.object(
        dependencies, "decode_token",
        return_value={"sub": str(user.user_id)},
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=creds, db=db)

    assert exc.value.status_code == 401
