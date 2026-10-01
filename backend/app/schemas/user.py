from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=80)
    phone_number: str
    name: str | None = None
    email: EmailStr | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    phone_number: str
    email: str | None = None
    name: str | None = None
    status: str
    accepted_terms: bool
    accepted_privacy: bool = False
    is_phone_verified: bool = False
    is_email_verified: bool = False
    preferred_language: str = "en"
    created_at: datetime


class UserDeletionOtpRequest(BaseModel):
    channel: Literal["email"] = "email"


class UserDeletionConfirmRequest(BaseModel):
    channel: Literal["email"] = "email"
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge_id: str | None = Field(default=None, min_length=30, max_length=64)
