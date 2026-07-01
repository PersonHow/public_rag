"""
app/schemas/chunk.py

Gemini Flash 輸出的 chunk 驗證 schema。
embed_text 不能為空字串或 null（§8-1 步驟 5）。

Phase 4：新增 face 欄位（加工面向，nullable）。
"""
from typing import Optional

from pydantic import BaseModel, field_validator


class GeminiChunkOutput(BaseModel):
    """Gemini Flash 輸出的單一 chunk 結構（後端不輸出的欄位在此不驗）。"""

    # Gemini 填入
    product_name: Optional[str] = None
    product_id: Optional[str] = None
    material: Optional[str] = None
    dimensions: Optional[str] = None
    specs: Optional[str] = None
    situation: Optional[str] = None
    action: Optional[str] = None
    reason: Optional[str] = None
    applies_to: Optional[str] = None
    # doc_type 不信任 Gemini 輸出：實際類別由後端依副檔名（Document.doc_type）注入，
    # 存 DB 時用的是 document.doc_type，這裡只接收、不強制。允許 null 避免整批連坐失敗。
    doc_type: Optional[str] = None
    case_id: Optional[str] = None
    embed_text: str  # NOT NULL，驗證在下方

    # Phase 4 新增：加工面向（第一面 / 第二面 / null）
    # 原始文件怎麼寫就怎麼填，Gemini 不 normalize
    face: Optional[str] = None

    # 固定 null（後處理注入）
    code_gcs_path: Optional[str] = None
    drawing_gcs_path: Optional[str] = None

    @field_validator("embed_text")
    @classmethod
    def embed_text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("embed_text 不能為空字串或 null")
        return v.strip()

    model_config = {"extra": "ignore"}  # 忽略 Gemini 可能輸出的額外欄位


class GeminiChunkValidationError(BaseModel):
    """WARNING log 用：記錄驗證失敗的 chunk 細節（更新版決策 5）。"""

    index: int
    product_name: Optional[str]
    embed_text: Optional[str]
    error: str


class ChunkPatch(BaseModel):
    """PATCH /sessions/{session_id}/chunks/{chunk_id} 的 request body。

    所有欄位 Optional，僅 model_dump(exclude_unset=True) 更新有給的欄位。
    禁止編輯 chunk_id / doc_id / company_id / rule_version / chunk_index /
    code_gcs_path / drawing_gcs_path / created_at —— extra=forbid 在 422 擋掉。
    embed_text / doc_type 給定時不可為空；其他文字欄位空字串視為 None（清空）。
    """

    product_name: Optional[str] = None
    product_id: Optional[str] = None
    material: Optional[str] = None
    dimensions: Optional[str] = None
    specs: Optional[str] = None
    situation: Optional[str] = None
    action: Optional[str] = None
    reason: Optional[str] = None
    applies_to: Optional[str] = None
    case_id: Optional[str] = None
    doc_type: Optional[str] = None
    face: Optional[str] = None
    embed_text: Optional[str] = None

    model_config = {"extra": "forbid"}

    @field_validator("embed_text")
    @classmethod
    def _embed_text_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("embed_text 不能為空字串")
        return stripped

    @field_validator("doc_type")
    @classmethod
    def _doc_type_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("doc_type 不能為空字串")
        return stripped.lower()

    @field_validator(
        "product_name", "product_id", "material", "dimensions", "specs",
        "situation", "action", "reason", "applies_to", "case_id", "face",
    )
    @classmethod
    def _empty_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = v.strip()
        return stripped if stripped else None
