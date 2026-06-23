"""
app/routers/query.py

POST /query — 現場查詢 RAG（Phase 5）

查詢鏈路：
  問題 → embed_texts(RETRIEVAL_QUERY) → Qdrant search(company_id filter)
       → top-k chunks → RAG prompt → Gemini Flash → 條列式回答

company_id 永遠從 JWT token 取。
Qdrant company_id filter 強制帶入（多租戶隔離）。
"""
import asyncio
import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.conversation import ConversationHistory
from app.models.document import Document
from app.schemas.auth import CurrentUser
from app.schemas.query import QueryRequest, QueryResponse, SourceItem
from app.services.ai.embedding import embed_texts
from app.services.ai.gemini import generate_answer
from app.services.ai.qdrant_service import search
from app.services.storage.gcs import generate_signed_url
from app.prompts.query_prompt import SYSTEM_PROMPT, build_rag_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _save_history(
    db: AsyncSession,
    *,
    company_id: str,
    user_id: UUID,
    question: str,
    answer: str,
    sources: list["SourceItem"],
    top_k: int,
    elapsed_ms: int,
) -> None:
    """寫入查詢歷史（best-effort，失敗不影響查詢回應）。

    sources 只存結構性欄位；code_download_url 是 1 小時過期的 signed URL，不存。
    """
    try:
        db.add(
            ConversationHistory(
                company_id=UUID(company_id),
                user_id=user_id,
                question=question,
                answer=answer,
                sources=[
                    {
                        "doc_filename": s.doc_filename,
                        "chunk_context": s.chunk_context,
                        "score": s.score,
                    }
                    for s in sources
                ],
                top_k=top_k,
                elapsed_ms=elapsed_ms,
            )
        )
        await db.flush()
    except Exception as e:
        logger.warning(
            f"查詢歷史寫入失敗（已略過）: {e}",
            extra={
                "phase": "phase6",
                "service": "query",
                "company_id": company_id,
                "session_id": None,
            },
        )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("", response_model=QueryResponse)
async def query_knowledge(
    req: QueryRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: Optional[str] = Query(default=None),  # superadmin 專用
) -> QueryResponse:

    t_start = time.monotonic()

    # superadmin 必須帶 company_id query param
    if current_user.role == "superadmin":
        if not company_id:
            raise HTTPException(status_code=400, detail="superadmin 查詢需指定 company_id")
        effective_company_id = company_id
    else:
        effective_company_id = str(current_user.company_id)

    logger.info(
        f"查詢開始 question_length={len(req.question)} top_k={req.top_k}",
        extra={
            "phase": "phase5",
            "service": "query",
            "company_id": effective_company_id,
            "session_id": None,
        },
    )

    # ── 1. 問題向量化 ─────────────────────────────────────────────────────
    vectors = await embed_texts([req.question], task_type="RETRIEVAL_QUERY")
    query_vector = vectors[0]

    # ── 2. Qdrant 語意搜尋（強制 company_id filter）────────────────────────
    # search() 是同步 blocking 呼叫（QdrantClient），用 run_in_executor 包裝避免卡住 event loop
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        lambda: search(
            query_vector=query_vector,
            company_id=effective_company_id,
            top_k=req.top_k,
        ),
    )

    if not results:
        elapsed = int((time.monotonic() - t_start) * 1000)
        logger.info(
            "查詢無結果，Qdrant 回傳 0 筆結果",
            extra={
                "phase": "phase5",
                "service": "query",
                "company_id": effective_company_id,
                "session_id": None,
            },
        )
        no_result_answer = "資料庫中未找到與此問題相關的知識，請確認問題描述或聯繫管理員補充資料。"
        await _save_history(
            db,
            company_id=effective_company_id,
            user_id=current_user.user_id,
            question=req.question,
            answer=no_result_answer,
            sources=[],
            top_k=req.top_k,
            elapsed_ms=elapsed,
        )
        return QueryResponse(
            answer=no_result_answer,
            sources=[],
            elapsed_ms=elapsed,
        )

    # ── 3. 批次查 doc_filename（一次 SQL）────────────────────────────────
    doc_ids = list({
        r["payload"]["doc_id"]
        for r in results
        if r["payload"].get("doc_id")
    })
    doc_id_to_filename: dict[str, str] = {}
    # 過濾掉格式異常的 doc_id（避免單一壞 payload 讓整個查詢 500）
    valid_doc_uuids = []
    for d in doc_ids:
        try:
            valid_doc_uuids.append(UUID(d))
        except (ValueError, TypeError):
            logger.warning(f"Qdrant payload 含無效 doc_id，已跳過: {d}")
    if valid_doc_uuids:
        stmt = select(Document.doc_id, Document.filename).where(
            Document.doc_id.in_(valid_doc_uuids)
        )
        rows = await db.execute(stmt)
        for doc_id, filename in rows:
            doc_id_to_filename[str(doc_id)] = filename

    # ── 4. 組 RAG Prompt → Gemini Flash 生成 ─────────────────────────────
    user_prompt = build_rag_prompt(req.question, results, doc_id_to_filename)
    answer = await generate_answer(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    # ── 5. 組 Sources（含 GCS 簽名 URL）──────────────────────────────────
    sources: list[SourceItem] = []

    for r in results:
        p = r["payload"]
        doc_id = p.get("doc_id", "")
        filename = doc_id_to_filename.get(doc_id, "未知文件")

        # chunk_context：product_name / doc_type
        ctx_parts = [x for x in [p.get("product_name"), p.get("doc_type")] if x]
        chunk_context = " / ".join(ctx_parts) if ctx_parts else filename

        # GCS 簽名 URL（1 小時有效）
        code_url: str | None = None
        if p.get("code_gcs_path"):
            try:
                code_url = generate_signed_url(p["code_gcs_path"], expiration_seconds=3600)
            except Exception as e:
                logger.warning(
                    f"signed URL 生成失敗, code_gcs_path={p['code_gcs_path']} error={e}",
                    extra={
                        "phase": "phase5",
                        "service": "query",
                        "company_id": effective_company_id,
                        "session_id": None,
                    },
                )

        sources.append(
            SourceItem(
                doc_filename=filename,
                chunk_context=chunk_context,
                score=round(r["score"], 4),
                code_download_url=code_url,
            )
        )

    elapsed = int((time.monotonic() - t_start) * 1000)

    if elapsed > 2000:
        logger.warning(
            f"查詢超過 2 秒, elapsed_ms={elapsed}",
            extra={
                "phase": "phase5",
                "service": "query",
                "company_id": effective_company_id,
                "session_id": None,
            },
        )
    else:
        logger.info(
            f"查詢完成, elapsed_ms={elapsed} sources={len(sources)}",
            extra={
                "phase": "phase5",
                "service": "query",
                "company_id": effective_company_id,
                "session_id": None,
            },
        )

    await _save_history(
        db,
        company_id=effective_company_id,
        user_id=current_user.user_id,
        question=req.question,
        answer=answer,
        sources=sources,
        top_k=req.top_k,
        elapsed_ms=elapsed,
    )

    return QueryResponse(answer=answer, sources=sources, elapsed_ms=elapsed)
