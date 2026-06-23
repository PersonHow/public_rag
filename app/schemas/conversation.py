import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: uuid.UUID
    question: str
    answer: str
    sources: list[dict] | None = None
    top_k: int
    elapsed_ms: int
    created_at: datetime


class PaginatedConversationResponse(BaseModel):
    total: int
    limit: int
    offset: int
    data: list[ConversationRecord]
