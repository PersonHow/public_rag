"""
app/routers/sessions.py

GET  /sessions/{session_id}         — 查詢 session 狀態（Mirror View polling 用）
GET  /sessions/{session_id}/chunks  — 取 session 所有 chunks（Mirror View 預覽）
POST /sessions/{session_id}/confirm — 管理員確認
POST /sessions/{session_id}/reject  — 管理員拒絕
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.session import IngestionSession
from app.schemas.upload import ConfirmResponse, SessionStatusResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()
logger = get_logger("sessions")


async def _get_session_or_404(session_id: uuid.UUID, db: AsyncSession) -> IngestionSession:
    result = await db.execute(
        select(IngestionSession).where(IngestionSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} 不存在")
    return session


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SessionStatusResponse:
    """Mirror View polling 用：取得 session 目前狀態。"""
    session = await _get_session_or_404(session_id, db)
    return SessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        fail_reason=session.fail_reason,
        preview_confirmed=session.preview_confirmed,
    )


@router.get("/{session_id}/chunks")
async def get_session_chunks(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Mirror View 預覽用：回傳 session 下所有 chunks 和 document 資訊。
    包含 has_low_confidence 供前端顯示橘色警示。
    """
    session = await _get_session_or_404(session_id, db)

    # 取 documents（含 OCR confidence 資訊）
    docs_result = await db.execute(
        select(Document).where(Document.session_id == session_id)
    )
    documents = docs_result.scalars().all()

    # 取 chunks
    chunks_result = await db.execute(
        select(Chunk).where(
            Chunk.doc_id.in_([d.doc_id for d in documents])
        )
    )
    chunks = chunks_result.scalars().all()

    return {
        "session_id": str(session_id),
        "status": session.status,
        "documents": [
            {
                "doc_id": str(d.doc_id),
                "filename": d.filename,
                "doc_type": d.doc_type,
                "has_low_confidence": d.has_low_confidence,
                "min_confidence": d.min_confidence,
                "gcs_raw_path": d.gcs_raw_path,
            }
            for d in documents
        ],
        "chunks": [_chunk_to_dict(c) for c in chunks],
        "chunk_count": len(chunks),
    }


@router.post("/{session_id}/confirm", response_model=ConfirmResponse)
async def confirm_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ConfirmResponse:
    """
    管理員 Mirror View 確認（§11-3）。
    status: pending_preview → confirmed
    Phase 2：confirmed_by 從 JWT token 取真實 user_id。
    """
    session = await _get_session_or_404(session_id, db)

    if session.status != "pending_preview":
        raise HTTPException(
            status_code=400,
            detail=f"只有 pending_preview 狀態可以確認，目前狀態：{session.status}",
        )

    session.status = "confirmed"
    session.preview_confirmed = True
    await db.flush()

    # Phase 2 接縫點：confirmed_by 改為 current_user.user_id
    confirmed_by = "dev-admin"

    logger.info(
        "Mirror View 確認",
        extra={
            "session_id": str(session_id),
            "confirmed_by": confirmed_by,
        },
    )

    return ConfirmResponse(
        session_id=session_id,
        status="confirmed",
        message="Session 已確認，等待批次寫入（Phase 4 實作）",
    )


@router.post("/{session_id}/reject", response_model=ConfirmResponse)
async def reject_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ConfirmResponse:
    """
    管理員拒絕：status → failed，可重新上傳。
    """
    session = await _get_session_or_404(session_id, db)

    if session.status not in ("pending_preview", "confirmed"):
        raise HTTPException(
            status_code=400,
            detail=f"目前狀態 {session.status} 不可拒絕",
        )

    session.status = "failed"
    session.fail_reason = "管理員拒絕"
    await db.flush()

    logger.info(
        "Mirror View 拒絕",
        extra={"session_id": str(session_id), "confirmed_by": "dev-admin"},
    )

    return ConfirmResponse(
        session_id=session_id,
        status="failed",
        message="Session 已拒絕，請重新上傳",
    )


def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.chunk_id),
        "doc_id": str(chunk.doc_id),
        "company_id": chunk.company_id,
        "doc_type": chunk.doc_type,
        "rule_version": chunk.rule_version,
        "embed_text": chunk.embed_text,
        "product_name": chunk.product_name,
        "product_id": chunk.product_id,
        "material": chunk.material,
        "dimensions": chunk.dimensions,
        "specs": chunk.specs,
        "situation": chunk.situation,
        "action": chunk.action,
        "reason": chunk.reason,
        "applies_to": chunk.applies_to,
        "case_id": chunk.case_id,
        "code_gcs_path": chunk.code_gcs_path,
        "drawing_gcs_path": chunk.drawing_gcs_path,
        "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
    }
