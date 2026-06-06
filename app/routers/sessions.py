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
import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, get_session_factory
from app.core.logging import get_logger
from app.core.dependencies import require_roles
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.session import IngestionSession
from app.schemas.upload import ConfirmResponse, SessionStatusResponse
from app.schemas.auth import CurrentUser
from app.schemas.chunk import ChunkPatch

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()
logger = get_logger("sessions")

_confirm_allowed = require_roles("superadmin")


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
    current_user: CurrentUser = Depends(_confirm_allowed),
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
    current_user: CurrentUser = Depends(_confirm_allowed),
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


@router.patch("/{session_id}/chunks/{chunk_id}")
async def patch_session_chunk(
    session_id: uuid.UUID,
    chunk_id: uuid.UUID,
    body: ChunkPatch,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(_confirm_allowed),
) -> dict[str, Any]:
    """
    v2 預覽階段修正 chunk 欄位。

    僅在 session.status == pending_preview 開放（其他狀態 409）。此階段 Qdrant 尚未
    有任何向量，故不需重新 embed、不需碰 Qdrant —— 純粹更新 PostgreSQL chunks 列。

    權限（v2 變更）：
      - 僅 superadmin（company_admin / field_user 皆 403，已由 require_roles 擋）
    """
    session = await _get_session_or_404(session_id, db)

    if session.status != "pending_preview":
        raise HTTPException(
            status_code=409,
            detail=f"僅能在預覽階段編輯 chunk（目前狀態：{session.status}）",
        )

    chunk_result = await db.execute(select(Chunk).where(Chunk.chunk_id == chunk_id))
    chunk = chunk_result.scalar_one_or_none()
    if not chunk:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} 不存在")

    doc_session_result = await db.execute(
        select(Document.session_id).where(Document.doc_id == chunk.doc_id)
    )
    if doc_session_result.scalar_one_or_none() != session_id:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} 不屬於此 session")

    if current_user.role != "superadmin" and chunk.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="無權編輯其他公司的 chunk")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _chunk_to_dict(chunk)

    for field_name, new_value in updates.items():
        setattr(chunk, field_name, new_value)

    await db.flush()

    logger.info(
        "Chunk 預覽編輯",
        extra={
            "session_id": str(session_id),
            "chunk_id": str(chunk_id),
            "edited_by": str(current_user.user_id),
            "company_id": str(current_user.company_id) if current_user.company_id else None,
            "fields": list(updates.keys()),
        },
    )

    return _chunk_to_dict(chunk)


@router.post("/{session_id}/confirm", response_model=ConfirmResponse)
async def confirm_session(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
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

    logger.info(
        "Mirror View 確認",
        extra={
            "session_id": str(session_id),
            "confirmed_by": str(current_user.user_id),
            "company_id": str(current_user.company_id) if current_user.company_id else None,
            "phase": "phase4",
        },
    )

    await _enqueue_ingest_with_fallback(session_id, background_tasks)

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
    current_user: CurrentUser = Depends(_confirm_allowed),
) -> list[SessionStatusResponse]:
    """
    Sessions 列表（v2：僅 superadmin）。
    - 可搭配 ?company_id= query param 過濾單一租戶
    """
    query = select(IngestionSession)
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

async def _enqueue_ingest_with_fallback(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    max_retries: int = 3,
) -> None:
    """
    先嘗試 Cloud Tasks 最多 max_retries 次；全部失敗才改用 BackgroundTask。
    enqueue_ingest_chunks 是同步 blocking call，用 run_in_executor 包裝。
    """
    from app.services.storage.tasks import enqueue_ingest_chunks

    loop = asyncio.get_event_loop()
    log_extra = {"session_id": str(session_id)}

    logger.info(
        "ingest-chunks Cloud Tasks 排程開始",
        extra={
            **log_extra,
            "queue":       settings.CLOUD_TASKS_QUEUE,
            "worker_url":  f"{settings.WORKER_BASE_URL}/internal/tasks/ingest-chunks",
            "max_retries": max_retries,
        },
    )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        logger.info(
            f"ingest-chunks Cloud Tasks 嘗試中（第 {attempt}/{max_retries} 次）",
            extra={**log_extra, "attempt": attempt},
        )
        try:
            task_name = await loop.run_in_executor(
                None,
                lambda: enqueue_ingest_chunks(session_id),
            )
            logger.info(
                f"ingest-chunks Cloud Tasks 排程成功（第 {attempt}/{max_retries} 次）",
                extra={**log_extra, "task_name": task_name},
            )
            return
        except Exception as e:
            last_error = e
            logger.warning(
                f"ingest-chunks Cloud Tasks 排程失敗（第 {attempt}/{max_retries} 次）: {type(e).__name__}: {e}",
                extra={**log_extra, "attempt": attempt, "error": str(e)},
            )
            if attempt < max_retries:
                await asyncio.sleep(0.5)

    logger.error(
        f"ingest-chunks Cloud Tasks {max_retries} 次全部失敗，改用 BackgroundTask",
        extra={**log_extra, "final_error": str(last_error)},
    )
    background_tasks.add_task(_ingest_chunks_background, session_id)


async def _ingest_chunks_background(session_id: uuid.UUID) -> None:
    """BackgroundTask fallback：Cloud Tasks 無法派送時，在同一 container 內執行向量化。"""
    from app.services.ai.embedding import embed_texts
    from app.services.ai.qdrant_service import (
        delete_chunks_by_ids,
        normalize_product_name_by_doc,
        upsert_chunks,
    )
    from app.routers.internal.tasks import _mark_session_failed

    log_extra = {"session_id": str(session_id), "via": "background_task"}

    async with get_session_factory()() as db:
        try:
            session_result = await db.execute(
                select(IngestionSession).where(IngestionSession.session_id == session_id)
            )
            session = session_result.scalar_one_or_none()
            if not session:
                logger.error("_ingest_chunks_background: session 不存在", extra=log_extra)
                return

            company_id_str = str(session.company_id)
            log_extra["company_id"] = company_id_str

            if session.status not in ("confirmed", "processing"):
                logger.info(
                    f"Session 狀態 {session.status}，跳過 ingest-chunks",
                    extra=log_extra,
                )
                return

            docs_result = await db.execute(
                select(Document.doc_id).where(Document.session_id == session_id)
            )
            doc_ids = [row[0] for row in docs_result.all()]

            if not doc_ids:
                logger.warning("Session 沒有任何 document，跳過", extra=log_extra)
                session.status = "done"
                await db.commit()
                return

            chunks_result = await db.execute(
                select(Chunk).where(Chunk.doc_id.in_(doc_ids))
            )
            chunks = list(chunks_result.scalars().all())

            if not chunks:
                logger.warning("Session 沒有任何 chunk，跳過", extra=log_extra)
                session.status = "done"
                await db.commit()
                return

            logger.info(
                "ingest-chunks BackgroundTask 開始",
                extra={**log_extra, "chunk_count": len(chunks)},
            )
            session.status = "processing"
            await db.flush()

            chunk_ids = [str(c.chunk_id) for c in chunks]

            try:
                vectors = await embed_texts(
                    [c.embed_text for c in chunks],
                    task_type="RETRIEVAL_DOCUMENT",
                )
            except Exception as e:
                logger.error(f"embed_texts 失敗: {e}", extra=log_extra)
                await _mark_session_failed(session, db, reason=f"embedding failed: {e}", log_extra=log_extra)
                await db.commit()
                return

            points = [
                {
                    "id": str(c.chunk_id),
                    "vector": vectors[i],
                    "payload": {
                        "company_id":   str(c.company_id),
                        "chunk_id":     str(c.chunk_id),
                        "doc_id":       str(c.doc_id),
                        "doc_type":     c.doc_type,
                        "rule_version": c.rule_version,
                        "face":         c.face,
                        "product_name": c.product_name,
                        "product_id":   c.product_id,
                        "situation":    c.situation,
                        "action":       c.action,
                        "embed_text":   c.embed_text,
                    },
                }
                for i, c in enumerate(chunks)
            ]

            try:
                upsert_chunks(points)
            except Exception as e:
                logger.error(f"Qdrant upsert 失敗，嘗試回滾: {e}", extra=log_extra)
                try:
                    delete_chunks_by_ids(chunk_ids)
                except Exception as rollback_err:
                    logger.error(f"Qdrant rollback 失敗: {rollback_err}", extra=log_extra)
                await _mark_session_failed(session, db, reason=f"qdrant upsert failed: {e}", log_extra=log_extra)
                await db.commit()
                return

            total_fixed = 0
            for did in doc_ids:
                total_fixed += normalize_product_name_by_doc(str(did), company_id_str)
            if total_fixed > 0:
                logger.info(
                    "product_name 正規化完成",
                    extra={**log_extra, "total_fixed": total_fixed},
                )

            session.status = "done"
            await db.commit()

            logger.info(
                "ingest-chunks BackgroundTask 完成",
                extra={**log_extra, "chunk_count": len(chunks)},
            )

        except Exception as e:
            logger.error(f"_ingest_chunks_background 未預期錯誤: {e}", extra=log_extra)
            await db.rollback()
            async with get_session_factory()() as db2:
                s2 = (await db2.execute(
                    select(IngestionSession).where(IngestionSession.session_id == session_id)
                )).scalar_one_or_none()
                if s2:
                    await _mark_session_failed(s2, db2, reason=f"background_task: {e}", log_extra=log_extra)
                    await db2.commit()


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
