from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None


class LoginResponse(BaseModel):
    """登入成功的 response body：只含 UI 需要的身分資訊，access_token 改放 httpOnly cookie。"""
    role: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None


class CurrentUser(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    company_id: Optional[uuid.UUID] = None
