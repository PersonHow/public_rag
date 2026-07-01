"""
GeminiChunkOutput 驗證行為的回歸測試。

背景：Gemini Flash 常把 doc_type 填成 null（prompt 允許「無值填 null」），
舊 schema 卻要求 doc_type 非空 → 整批 chunk 連坐驗證失敗 → 全有全無重試 3 次
都中 → 預覽永遠失敗（實例：偏心栓塞閥文本 PV0500E.docx）。

真正的文件類別由後端依副檔名（document.doc_type）決定並寫入 DB，Gemini 輸出的
doc_type 從不入庫，因此這欄必須容許 null。但 embed_text 是唯一被向量化的欄位，
仍必須非空。本檔用實際 pipeline 用到的 _validate_chunks 驗證這兩條規則。
"""
from app.services.ai.gemini import _validate_chunks


def _chunk(**overrides):
    base = {
        "product_name": "偏心栓塞閥",
        "product_id": "PV0500E",
        "material": "球墨鑄鐵FCD500",
        "dimensions": "DN500mm",
        "specs": None,
        "situation": None,
        "action": None,
        "reason": None,
        "applies_to": None,
        "doc_type": None,
        "case_id": None,
        "face": None,
        "embed_text": "偏心栓塞閥 PV0500E 的產品規格為：材料球墨鑄鐵FCD500，尺寸DN500mm。",
    }
    base.update(overrides)
    return base


def test_null_doc_type_whole_batch_passes():
    """整批 chunk 的 doc_type 皆為 null 時不得連坐失敗（PV0500E 主因）。"""
    valid, errors = _validate_chunks([_chunk() for _ in range(15)])

    assert len(errors) == 0
    assert len(valid) == 15
    assert valid[0].doc_type is None


def test_missing_doc_type_key_passes():
    """Gemini 完全省略 doc_type 欄位也要能通過（Optional 預設 None）。"""
    item = _chunk()
    del item["doc_type"]

    valid, errors = _validate_chunks([item])

    assert len(errors) == 0
    assert valid[0].doc_type is None


def test_empty_embed_text_still_fails():
    """embed_text 為空白仍須被擋下——這是不能放寬的核心驗證。"""
    valid, errors = _validate_chunks([_chunk(embed_text="   ")])

    assert len(valid) == 0
    assert len(errors) == 1
    assert "embed_text" in errors[0].error


def test_valid_chunk_strips_embed_text():
    """正常 chunk 通過，且 embed_text 前後空白被 strip。"""
    valid, errors = _validate_chunks([_chunk(embed_text="  有效內容  ", doc_type="docx")])

    assert len(errors) == 0
    assert valid[0].embed_text == "有效內容"
