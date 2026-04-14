"""
tests/test_gemini_parser.py

Gemini Flash JSON 防禦邏輯單元測試（§8-1 最脆弱的點）。
測試各種髒輸出情境：markdown fence、前綴文字、空 embed_text 等。
"""
import json
import pytest
from pydantic import ValidationError

from app.services.gemini import _extract_json_array
from app.schemas.chunk import GeminiChunkOutput


VALID_CHUNK = {
    "product_name": "球閥",
    "product_id": "BV-001",
    "material": "不銹鋼 316L",
    "dimensions": "DN50",
    "specs": None,
    "situation": "球閥洩漏",
    "action": "更換密封圈",
    "reason": "超溫造成變形",
    "applies_to": "BV 系列",
    "doc_type": "pdf",
    "case_id": None,
    "embed_text": "球閥 BV-001 在高溫環境下發生洩漏，需更換耐高溫 PTFE 密封圈。",
    "code_gcs_path": None,
    "drawing_gcs_path": None,
}


class TestExtractJsonArray:
    """_extract_json_array 防禦邏輯測試。"""

    def test_clean_json(self):
        raw = json.dumps([VALID_CHUNK])
        result = _extract_json_array(raw)
        parsed = json.loads(result)
        assert len(parsed) == 1

    def test_with_markdown_fence(self):
        raw = f"```json\n{json.dumps([VALID_CHUNK])}\n```"
        result = _extract_json_array(raw)
        parsed = json.loads(result)
        assert len(parsed) == 1

    def test_with_markdown_fence_no_lang(self):
        raw = f"```\n{json.dumps([VALID_CHUNK])}\n```"
        result = _extract_json_array(raw)
        parsed = json.loads(result)
        assert len(parsed) == 1

    def test_with_prefix_text(self):
        raw = f"以下是轉換結果：\n\n{json.dumps([VALID_CHUNK])}"
        result = _extract_json_array(raw)
        parsed = json.loads(result)
        assert len(parsed) == 1

    def test_with_prefix_and_fence(self):
        raw = f"好的，以下是結果：\n```json\n{json.dumps([VALID_CHUNK])}\n```\n請確認。"
        result = _extract_json_array(raw)
        parsed = json.loads(result)
        assert len(parsed) == 1

    def test_whitespace_stripping(self):
        raw = f"\n\n  {json.dumps([VALID_CHUNK])}  \n\n"
        result = _extract_json_array(raw)
        parsed = json.loads(result)
        assert len(parsed) == 1

    def test_multiple_chunks(self):
        chunks = [VALID_CHUNK, {**VALID_CHUNK, "product_name": "蝶閥"}]
        raw = json.dumps(chunks)
        result = _extract_json_array(raw)
        parsed = json.loads(result)
        assert len(parsed) == 2

    def test_no_array_raises(self):
        with pytest.raises(ValueError, match="找不到 JSON array 邊界"):
            _extract_json_array("這裡沒有 JSON array")

    def test_object_not_array_raises(self):
        raw = json.dumps({"key": "value"})
        # _extract_json_array 只找 [ ]，object 用 { } 所以會拋出 ValueError
        with pytest.raises(ValueError):
            _extract_json_array(raw)


class TestGeminiChunkOutputValidation:
    """Pydantic schema 驗證測試。"""

    def test_valid_chunk(self):
        chunk = GeminiChunkOutput.model_validate(VALID_CHUNK)
        assert chunk.embed_text == VALID_CHUNK["embed_text"]
        assert chunk.code_gcs_path is None

    def test_empty_embed_text_raises(self):
        bad = {**VALID_CHUNK, "embed_text": ""}
        with pytest.raises(ValidationError) as exc_info:
            GeminiChunkOutput.model_validate(bad)
        assert "embed_text" in str(exc_info.value)

    def test_whitespace_only_embed_text_raises(self):
        bad = {**VALID_CHUNK, "embed_text": "   "}
        with pytest.raises(ValidationError):
            GeminiChunkOutput.model_validate(bad)

    def test_null_embed_text_raises(self):
        bad = {**VALID_CHUNK, "embed_text": None}
        with pytest.raises(ValidationError):
            GeminiChunkOutput.model_validate(bad)

    def test_missing_embed_text_raises(self):
        bad = {k: v for k, v in VALID_CHUNK.items() if k != "embed_text"}
        with pytest.raises(ValidationError):
            GeminiChunkOutput.model_validate(bad)

    def test_nullable_fields_accept_none(self):
        chunk = GeminiChunkOutput.model_validate({
            **VALID_CHUNK,
            "product_name": None,
            "situation": None,
            "case_id": None,
        })
        assert chunk.product_name is None

    def test_extra_fields_ignored(self):
        """Gemini 可能輸出多餘欄位，應被 ignore。"""
        chunk = GeminiChunkOutput.model_validate({
            **VALID_CHUNK,
            "unexpected_field": "should be ignored",
        })
        assert not hasattr(chunk, "unexpected_field")

    def test_embed_text_stripped(self):
        """embed_text 前後空白應被去除。"""
        chunk = GeminiChunkOutput.model_validate({
            **VALID_CHUNK,
            "embed_text": "  有效的 embed text  ",
        })
        assert chunk.embed_text == "有效的 embed text"
