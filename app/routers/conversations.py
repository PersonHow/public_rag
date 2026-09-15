"""
app/routers/conversations.py

GET /conversations         — 查詢歷史列表（分頁）
GET /conversations/{id}    — 單筆查詢歷史

一般使用者只看自己的紀錄；superadmin 可用 ?company_id= 過濾指定租戶。
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.conversation import ConversationHistory
from app.schemas.auth import CurrentUser
from app.schemas.conversation import ConversationRecord, PaginatedConversationResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=PaginatedConversationResponse)
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    company_id: Optional[uuid.UUID] = Query(default=None),  # superadmin 專用
) -> PaginatedConversationResponse:
    base = select(ConversationHistory)

    if current_user.role == "superadmin":
        if company_id is not None:
            base = base.where(ConversationHistory.company_id == company_id)
    else:
        base = base.where(ConversationHistory.user_id == current_user.user_id)

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(ConversationHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return PaginatedConversationResponse(
        total=total,
        limit=limit,
        offset=offset,
        data=[ConversationRecord.model_validate(r) for r in rows],
    )


@router.get("/{conversation_id}", response_model=ConversationRecord)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationRecord:
    record = (
        await db.execute(
            select(ConversationHistory).where(
                ConversationHistory.conversation_id == conversation_id
            )
        )
    ).scalar_one_or_none()

    if record is None:
        raise HTTPException(status_code=404, detail="查詢歷史不存在")

    if current_user.role != "superadmin" and record.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="無權存取此查詢歷史")

    return ConversationRecord.model_validate(record)
