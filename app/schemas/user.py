from pydantic import BaseModel, EmailStr
from typing import Optional
from enum import Enum
import uuid


class UserRole(str, Enum):
    superadmin = "superadmin"
    company_admin = "company_admin"
    field_user = "field_user"


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: UserRole
    company_id: Optional[uuid.UUID] = None


class UserResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    company_id: Optional[uuid.UUID] = None
    is_active: bool

    class Config:
        from_attributes = True
