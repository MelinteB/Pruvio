from typing import Literal
from pydantic import BaseModel, EmailStr, Field


class PasswordLoginRequest(BaseModel):
    identifier: str
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge_id: str | None = Field(default=None, min_length=30, max_length=64)
    new_password: str = Field(min_length=8, max_length=256)


class ContactChangeRequest(BaseModel):
    value: str


class ContactChangeConfirmRequest(BaseModel):
    value: str
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge_id: str | None = Field(default=None, min_length=30, max_length=64)


class UserDeletionOtpRequest(BaseModel):
    channel: Literal["email"] = "email"


class UserDeletionConfirmRequest(BaseModel):
    channel: Literal["email"] = "email"
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge_id: str | None = Field(default=None, min_length=30, max_length=64)
