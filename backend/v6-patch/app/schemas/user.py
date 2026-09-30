from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    phone_number: str
    name: str | None = None
    email: EmailStr | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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
    channel: str = Field(pattern="^(email|phone)$")


class UserDeletionConfirmRequest(BaseModel):
    channel: str = Field(pattern="^(email|phone)$")
    code: str = Field(min_length=4, max_length=12)
