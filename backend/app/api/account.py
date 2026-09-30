from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.account import (
    PasswordLoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
)
from app.services.account_service import confirm_password_reset, request_password_reset
from app.services.auth_service import authenticate_with_password

router = APIRouter()


@router.post("/password/login")
def password_login(payload: PasswordLoginRequest, db: Session = Depends(get_db)):
    try:
        user = authenticate_with_password(db, payload.identifier, payload.password)
        return {
            "user_id": user.id,
            "name": user.name,
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
            "message": "Password reset code sent by email.",
            "debug_otp": result.get("debug_otp"),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/password-reset/confirm")
def password_reset_confirm(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    try:
        user = confirm_password_reset(db, str(payload.email), payload.code, payload.new_password)
        return {"user_id": user.id, "message": "Password updated successfully."}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
