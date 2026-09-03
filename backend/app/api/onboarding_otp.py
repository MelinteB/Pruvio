from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.onboarding_otp import (
    OTPStartRequest,
    OTPVerifyPhoneRequest,
    OTPVerifyEmailRequest,
    OTPResponse
)
from app.services.onboarding_otp_service import (
    start_otp_onboarding,
    verify_phone_otp,
    verify_email_otp
)


router = APIRouter()


@router.post(
    "/start",
    response_model=OTPResponse
)
def start_otp_verification(
    otp_data: OTPStartRequest,
    db: Session = Depends(get_db)
):
    try:
        return start_otp_onboarding(
            db=db,
            phone_number=otp_data.phone_number,
            display_name=otp_data.display_name,
            email=otp_data.email,
            accepted_terms=otp_data.accepted_terms
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@router.post(
    "/verify-phone",
    response_model=OTPResponse
)
def verify_phone(
    otp_data: OTPVerifyPhoneRequest,
    db: Session = Depends(get_db)
):
    try:
        return verify_phone_otp(
            db=db,
            phone_number=otp_data.phone_number,
            code=otp_data.code
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@router.post(
    "/verify-email",
    response_model=OTPResponse
)
def verify_email(
    otp_data: OTPVerifyEmailRequest,
    db: Session = Depends(get_db)
):
    try:
        return verify_email_otp(
            db=db,
            email=otp_data.email,
            code=otp_data.code
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )