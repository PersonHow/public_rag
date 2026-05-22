from pydantic import BaseModel
from typing import Optional
import uuid


class CompanyCreate(BaseModel):
    name: str
    industry: Optional[str] = None


class CompanyResponse(BaseModel):
    company_id: uuid.UUID
    name: str
    industry: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True
