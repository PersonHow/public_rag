"""
tests/test_user_password.py

UserCreate 密碼強度規則：至少 12 碼，含大小寫英文、數字、符號。
"""
import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate


def _make(password: str) -> UserCreate:
    return UserCreate(email="admin@onceagain.tw", password=password, role="superadmin")


def test_strong_password_accepted():
    assert _make("Str0ng!Passw0rd").password == "Str0ng!Passw0rd"


@pytest.mark.parametrize("password", [
    "Sh0rt!Pass",        # 10 碼
    "nouppercase123!",   # 缺大寫
    "NOLOWERCASE123!",   # 缺小寫
    "NoDigitsHere!!",    # 缺數字
    "NoSymbol12345a",    # 缺符號
])
def test_weak_password_rejected(password):
    with pytest.raises(ValidationError):
        _make(password)
