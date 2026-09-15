"""
tests/test_tap_matching.py

#10 回歸測試：_product_id_in_filename 以 token 邊界比對，
避免 product_id 子字串誤判而注入錯誤的 TAP 檔。
"""
from app.routers.internal.tasks import _product_id_in_filename


def test_exact_token_matches():
    assert _product_id_in_filename("A034-189010-1", "A034-189010-1_A_.tap")
    assert _product_id_in_filename("A034-189010-1", "A034-189010-1.tap")
    # 底線分隔的 face 後綴（真實檔名格式，見 _FACE_TO_SUFFIX）
    assert _product_id_in_filename("A034-189010-1", "op_A034-189010-1_B_.nc")


def test_numeric_extension_does_not_match():
    # 核心 bug：'-1' 不可命中 '-10' / '-11'
    assert not _product_id_in_filename("A034-189010-1", "A034-189010-10_A_.tap")
    assert not _product_id_in_filename("A034-189010-1", "A034-189010-11.tap")


def test_shorter_id_does_not_match_more_specific_file():
    # 'A034-189010' 不可命中更具體的 'A034-189010-1'
    assert not _product_id_in_filename("A034-189010", "A034-189010-1.tap")


def test_unrelated_filename():
    assert not _product_id_in_filename("A034-189010-1", "B999-000000-9.tap")
