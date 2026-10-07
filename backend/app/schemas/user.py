from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


UserStatus = Literal["pending_join", "active", "blocked"]


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


class UserAdminResponse(UserResponse):
    """Administrative user view. Secrets such as password hashes are never exposed."""

    accepted_terms_at: datetime | None = None
    terms_version: str | None = None
    accepted_privacy_at: datetime | None = None
    privacy_version: str | None = None
    marketing_opt_in: bool = False
    notifications_opt_in: bool = True
    revolut_payment_link: str | None = None
    payment_recipient_name: str | None = None
    payment_iban: str | None = None
    payment_bank_name: str | None = None
    payment_bic: str | None = None
    payment_note: str | None = None
    last_seen_at: datetime | None = None
    updated_at: datetime | None = None


class UserAdminUpdate(BaseModel):
    """
    Fields an administrator may change without OTP or verified-email checks.

    Legal acceptance timestamps/versions and password_hash are intentionally not
    editable through this API.
    """

    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=3, max_length=80)
    phone_number: str | None = Field(default=None, min_length=5, max_length=50)
    name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    status: UserStatus | None = None
    is_phone_verified: bool | None = None
    is_email_verified: bool | None = None
    preferred_language: str | None = Field(default=None, min_length=2, max_length=12)
    marketing_opt_in: bool | None = None
    notifications_opt_in: bool | None = None
    revolut_payment_link: str | None = Field(default=None, max_length=500)
    payment_recipient_name: str | None = Field(default=None, max_length=255)
    payment_iban: str | None = Field(default=None, max_length=64)
    payment_bank_name: str | None = Field(default=None, max_length=255)
    payment_bic: str | None = Field(default=None, max_length=32)
    payment_note: str | None = Field(default=None, max_length=255)


class UserDeletionOtpRequest(BaseModel):
    channel: Literal["email"] = "email"


class UserDeletionConfirmRequest(BaseModel):
    channel: Literal["email"] = "email"
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge_id: str | None = Field(default=None, min_length=30, max_length=64)
