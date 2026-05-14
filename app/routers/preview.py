"""
app/routers/preview.py

GET /sessions/{session_id}/documents/{doc_id}/full-text
提供單一文件的完整 chunks 預覽（依 chunk_index 排序）。
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.session import IngestionSession
from app.schemas.auth import CurrentUser
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/sessions", tags=["preview"])


class ChunkSummary(BaseModel):
    chunk_id: uuid.UUID
    chunk_index: Optional[int]
    product_name: Optional[str]
    product_id: Optional[str]
    situation: Optional[str]
    action: Optional[str]
    embed_text: str

    class Config:
        from_attributes = True


class DocumentFullTextResponse(BaseModel):
    doc_id: uuid.UUID
    filename: str
    chunk_count: int
    chunks: list[ChunkSummary]


@router.get("/{session_id}/documents/{doc_id}/full-text",
            response_model=DocumentFullTextResponse)
async def get_document_full_text(
    session_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. 驗證 session 屬於該 company
    session_result = await db.execute(
        select(IngestionSession).where(
            IngestionSession.session_id == session_id,
            IngestionSession.company_id == current_user.company_id,
        )
    )
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session 不存在")

    # 2. 取 document filename
    doc_result = await db.execute(
        select(Document).where(Document.doc_id == doc_id)
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document 不存在")

    # 3. 撈 chunks，chunk_index 優先，fallback created_at
    chunks_result = await db.execute(
        select(Chunk)
        .where(
            Chunk.doc_id == doc_id,
            Chunk.company_id == current_user.company_id,
        )
        .order_by(
            Chunk.chunk_index.asc().nulls_last(),
            Chunk.created_at.asc(),
        )
    )
    chunks = chunks_result.scalars().all()

    return DocumentFullTextResponse(
        doc_id=doc_id,
        filename=document.filename,
        chunk_count=len(chunks),
        chunks=[ChunkSummary.model_validate(c) for c in chunks],
    )
