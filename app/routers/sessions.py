"""
app/routers/sessions.py

GET  /sessions/{session_id}         — 查詢 session 狀態（Mirror View polling 用）
GET  /sessions/{session_id}/chunks  — 取 session 所有 chunks（Mirror View 預覽）
POST /sessions/{session_id}/confirm — 管理員確認（Phase 4：確認後自動派送 ingest-chunks）
POST /sessions/{session_id}/reject  — 管理員拒絕
GET  /sessions                      - 管理員查看所有 session 

Phase 5 變更：
  新增管理員查看 session 列表
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.dependencies import require_roles
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.session import IngestionSession
from app.schemas.upload import ConfirmResponse, SessionStatusResponse
from app.schemas.auth import CurrentUser
from app.services.storage.tasks import enqueue_ingest_chunks

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()
logger = get_logger("sessions")

_confirm_allowed = require_roles("superadmin", "company_admin")


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
    session = await _get_session_or_404(session_id, db)

    docs_result = await db.execute(
        select(Document).where(Document.session_id == session_id)
    )
    documents = docs_result.scalars().all()

    chunks_result = await db.execute(
        select(Chunk).where(Chunk.doc_id.in_([d.doc_id for d in documents]))
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
    current_user: CurrentUser = Depends(_confirm_allowed),
) -> ConfirmResponse:
    session = await _get_session_or_404(session_id, db)

    if session.status != "pending_preview":
        raise HTTPException(
            status_code=400,
            detail=f"只有 pending_preview 狀態可以確認，目前狀態：{session.status}",
        )

    session.status = "confirmed"
    session.preview_confirmed = True
    await db.flush()

    confirmed_by = str(current_user.user_id)

    logger.info(
        "Mirror View 確認",
        extra={
            "session_id": str(session_id),
            "confirmed_by": confirmed_by,
            "company_id": str(current_user.company_id) if current_user.company_id else None,
            "phase": "phase4",
        },
    )

    # ── Phase 4：派送 ingest-chunks Cloud Tasks ───────────────────────────
    try:
        task_name = enqueue_ingest_chunks(session_id)
        logger.info(
            "ingest-chunks 任務已派送",
            extra={"session_id": str(session_id), "task_name": task_name},
        )
    except Exception as e:
        # 派送失敗：回滾 session 狀態，讓管理員可以重試 confirm
        session.status = "pending_preview"
        session.preview_confirmed = False
        await db.flush()
        logger.error(
            f"ingest-chunks 任務派送失敗，session 已回滾至 pending_preview: {e}",
            extra={"session_id": str(session_id)},
        )
        raise HTTPException(
            status_code=503,
            detail="向量化任務派送失敗，請稍後重試確認",
        )

    return ConfirmResponse(
        session_id=session_id,
        status="confirmed",
        message="Session 已確認，向量化任務已派送",
    )


@router.post("/{session_id}/reject", response_model=ConfirmResponse)
async def reject_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(_confirm_allowed),
) -> ConfirmResponse:
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
        extra={
            "session_id": str(session_id),
            "rejected_by": str(current_user.user_id),
        },
    )

    return ConfirmResponse(
        session_id=session_id,
        status="failed",
        message="Session 已拒絕，請重新上傳",
    )


@router.get("", response_model=list[SessionStatusResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("superadmin", "company_admin")),
) -> list[SessionStatusResponse]:
    """
    Phase 5 變更：管理員查看所有 session 列表。
    - company_admin → 只能看自家公司
    - superadmin    → 看所有公司（可搭配 ?company_id= query param）
    """
    query = select(IngestionSession)
    if current_user.role != "superadmin":
        query = query.where(IngestionSession.company_id == current_user.company_id)
    result = await db.execute(query.order_by(IngestionSession.created_at.desc()).limit(100))
    sessions = result.scalars().all()
    return [
        SessionStatusResponse(
            session_id=s.session_id,
            status=s.status,
            fail_reason=s.fail_reason,
            preview_confirmed=s.preview_confirmed,
        )
        for s in sessions
    ]

def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.chunk_id),
        "doc_id": str(chunk.doc_id),
        "company_id": str(chunk.company_id),
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
        "face": chunk.face,                   # Phase 4 新增
        "code_gcs_path": chunk.code_gcs_path,
        "drawing_gcs_path": chunk.drawing_gcs_path,
        "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
    }
