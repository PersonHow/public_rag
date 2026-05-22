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
    material: Optional[str]
    dimensions: Optional[str]
    situation: Optional[str]
    action: Optional[str]
    reason: Optional[str]
    applies_to: Optional[str]
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
    # 1. 驗證 session 存在；superadmin 不過濾 company_id
    session_q = select(IngestionSession).where(
        IngestionSession.session_id == session_id
    )
    if current_user.role != "superadmin":
        session_q = session_q.where(
            IngestionSession.company_id == current_user.company_id
        )
    session_result = await db.execute(session_q)
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session 不存在")

    # 2. 取 document filename
    doc_result = await db.execute(
        select(Document).where(Document.doc_id == doc_id)
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document 不存在")

    # 3. 撈 chunks；superadmin 不過濾 company_id
    chunks_q = select(Chunk).where(Chunk.doc_id == doc_id)
    if current_user.role != "superadmin":
        chunks_q = chunks_q.where(Chunk.company_id == current_user.company_id)
    chunks_q = chunks_q.order_by(
        Chunk.chunk_index.asc().nulls_last(),
        Chunk.created_at.asc(),
    )
    chunks_result = await db.execute(chunks_q)
    chunks = chunks_result.scalars().all()

    return DocumentFullTextResponse(
        doc_id=doc_id,
        filename=document.filename,
        chunk_count=len(chunks),
        chunks=[ChunkSummary.model_validate(c) for c in chunks],
    )
