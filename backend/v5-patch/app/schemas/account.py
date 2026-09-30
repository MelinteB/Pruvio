from pydantic import BaseModel, EmailStr, Field


class PasswordLoginRequest(BaseModel):
    identifier: str
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8, max_length=256)


class ContactChangeRequest(BaseModel):
    value: str


class ContactChangeConfirmRequest(BaseModel):
    value: str
    code: str = Field(min_length=4, max_length=12)


class UserDeletionOtpRequest(BaseModel):
    channel: str = Field(pattern="^(email|phone)$")


class UserDeletionConfirmRequest(BaseModel):
    channel: str = Field(pattern="^(email|phone)$")
    code: str = Field(min_length=4, max_length=12)
