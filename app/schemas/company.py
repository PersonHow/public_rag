from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid


class CompanyCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None


class CompanyUpdate(CompanyCreate):
    pass


class CompanyResponse(BaseModel):
    company_id: uuid.UUID
    name: str
    industry: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    is_active: bool
    created_at: datetime
    # 只有列表 API 會算；單筆的建立／更新／停用回應不帶
    session_count: Optional[int] = None

    class Config:
        from_attributes = True
