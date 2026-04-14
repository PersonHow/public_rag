"""
tests/test_rule_version.py

rule_version 格式驗證（直接測試邏輯，不 import router 避免 DB 連線）。
"""
import re
from datetime import datetime, timezone


def generate_rule_version() -> str:
    """與 tasks.py 相同的邏輯，抽出供測試直接呼叫。"""
    now = datetime.now(timezone.utc)
    return now.strftime("v1-%y%m%d-%H%M")


def test_rule_version_format():
    version = generate_rule_version()
    pattern = r"^v1-\d{6}-\d{4}$"
    assert re.match(pattern, version), f"格式不符：{version}"


def test_rule_version_prefix():
    assert generate_rule_version().startswith("v1-")


def test_rule_version_length():
    version = generate_rule_version()
    assert len(version) == 14, f"長度應為 14，實際：{len(version)}（{version}）"
