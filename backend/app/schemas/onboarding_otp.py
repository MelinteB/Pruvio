from pydantic import BaseModel, EmailStr, Field


class OTPStartRequest(BaseModel):
    phone_number: str
    display_name: str | None = None
    email: EmailStr | None = None
    accepted_terms: bool = Field(default=False)


class OTPVerifyPhoneRequest(BaseModel):
    phone_number: str
    code: str


class OTPVerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class OTPResendRequest(BaseModel):
    phone_number: str
    destination_type: str = "phone"


class OTPResponse(BaseModel):
    user_id: int
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