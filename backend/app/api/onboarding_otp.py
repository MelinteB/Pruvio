from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.onboarding_otp import (
    OTPStartRequest,
    OTPVerifyEmailRequest,
    OTPResponse,
    OTPStatusResponse,
)
from app.services.onboarding_otp_service import (
    start_otp_onboarding,
    verify_email_otp,
    get_otp_onboarding_status
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
            username=otp_data.username,
            email=otp_data.email,
            accepted_terms=otp_data.accepted_terms,
            accepted_privacy=otp_data.accepted_privacy,
            password=otp_data.password
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@router.post("/verify-phone", include_in_schema=False)
def verify_phone_disabled():
    raise HTTPException(410, detail="Phone OTP is disabled. Verify your email instead.")


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
            code=otp_data.code,
            challenge_id=otp_data.challenge_id
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

@router.get(
    "/status",
    response_model=OTPStatusResponse
)
def get_otp_status(
    identifier: str = Query(..., description="Username or email address"),
    db: Session = Depends(get_db)
):
    try:
        return get_otp_onboarding_status(
            db=db,
            identifier=identifier
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )