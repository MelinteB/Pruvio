from pydantic import BaseModel, EmailStr, Field


class OTPStartRequest(BaseModel):
    phone_number: str
    username: str | None = Field(default=None, min_length=3, max_length=80)
    display_name: str | None = None
    email: EmailStr | None = None
    accepted_terms: bool = Field(default=False)
    accepted_privacy: bool = Field(default=False)
    password: str | None = Field(default=None, min_length=8, max_length=256)


class OTPVerifyPhoneRequest(BaseModel):
    phone_number: str
    code: str


class OTPVerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge_id: str = Field(min_length=30, max_length=64)


class OTPResendRequest(BaseModel):
    phone_number: str
    destination_type: str = "email"


class OTPResponse(BaseModel):
    user_id: int
    username: str | None = None
    challenge_id: str | None = None
    phone_number: str
    email: str | None = None
    display_name: str | None = None

    status: str
    accepted_terms: bool
    is_phone_verified: bool
    is_email_verified: bool

    action: str
    message: str

    phone_delivery: dict | None = None
    email_delivery: dict | None = None

    debug_phone_otp: str | None = None
    debug_email_otp: str | None = None


class OTPStatusResponse(BaseModel):
    user_id: int | None = None
    username: str | None = None
    phone_number: str
    email: str | None = None
    display_name: str | None = None

    status: str
    accepted_terms: bool
    is_phone_verified: bool
    is_email_verified: bool

    can_create_split_bill: bool
    action: str
    message: str