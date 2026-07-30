from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid


class LoginLogResponse(BaseModel):
    log_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    email: str
    company_id: Optional[uuid.UUID] = None
    event: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LoginLogListResponse(BaseModel):
    total: int
    items: List[LoginLogResponse]
