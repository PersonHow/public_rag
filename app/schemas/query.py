from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class SourceItem(BaseModel):
    doc_filename: str
    chunk_context: str          # "{product_name} / {doc_type}"
    score: float
    code_download_url: str | None = None
    code_filename: str | None = None   # 可下載的 TAP/NC 程式檔名（basename）


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    elapsed_ms: int
