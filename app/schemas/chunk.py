"""
app/schemas/chunk.py

Gemini Flash 輸出的 chunk 驗證 schema。
embed_text 不能為空字串或 null（§8-1 步驟 5）。
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
    doc_type: str
    case_id: Optional[str] = None
    embed_text: str  # NOT NULL，驗證在下方

    # 固定 null（後處理注入）
    code_gcs_path: Optional[str] = None
    drawing_gcs_path: Optional[str] = None

    @field_validator("embed_text")
    @classmethod
    def embed_text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("embed_text 不能為空字串或 null")
        return v.strip()

    @field_validator("doc_type")
    @classmethod
    def doc_type_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("doc_type 不能為空字串")
        return v.strip().lower()

    model_config = {"extra": "ignore"}  # 忽略 Gemini 可能輸出的額外欄位


class GeminiChunkValidationError(BaseModel):
    """WARNING log 用：記錄驗證失敗的 chunk 細節（更新版決策 5）。"""

    index: int
    product_name: Optional[str]
    embed_text: Optional[str]
    error: str
