from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.account import (
    PasswordLoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
)
from app.services.account_service import confirm_password_reset, request_password_reset
from app.services.auth_service import authenticate_with_password
from app.services.username_service import check_username_available
from app.services.trusted_device_service import DEVICE_COOKIE, is_trusted_device

router = APIRouter()


@router.post("/password/login")
def password_login(payload: PasswordLoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        user = authenticate_with_password(db, payload.identifier, payload.password)
        if not is_trusted_device(db, user, request.cookies.get(DEVICE_COOKIE)):
            return {"otp_required": True, "message": "Verify this new browser with OTP on the sign-in page."}
        return {
            "otp_required": False,
            "user_id": user.id,
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "phone_number": user.phone_number,
            "status": user.status,
            "message": "Password verified.",
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/password-reset/request")
def password_reset_request(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    try:
        result = request_password_reset(db, str(payload.email))
        return {
            "destination": result["destination"],
            "challenge_id": result["challenge_id"],
            "message": "Password reset delivery requested.",
            "delivery": result["delivery"],
            "debug_otp": result.get("debug_otp"),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/password-reset/confirm")
def password_reset_confirm(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    try:
        user = confirm_password_reset(db, str(payload.email), payload.code, payload.new_password, challenge_id=payload.challenge_id)
        return {"user_id": user.id, "message": "Password updated successfully."}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/username/available")
def username_available(username: str = Query(min_length=3, max_length=80), db: Session = Depends(get_db)):
    try:
        return {"available": True, "username": check_username_available(db, username)}
    except ValueError as error:
        return {"available": False, "message": str(error)}
