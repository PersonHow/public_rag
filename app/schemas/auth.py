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


class CurrentUser(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    company_id: Optional[uuid.UUID] = None
