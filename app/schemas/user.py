import re

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
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

    # 與前端 users.component 的 passwordRules 同步：至少 12 碼，含大小寫英文、數字、符號
    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("密碼至少需 12 碼")
        if not (re.search(r"[a-z]", v) and re.search(r"[A-Z]", v)
                and re.search(r"\d", v) and re.search(r"[^A-Za-z0-9]", v)):
            raise ValueError("密碼需包含大寫、小寫英文、數字與符號")
        return v


class UserResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    company_id: Optional[uuid.UUID] = None
    is_active: bool
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True
