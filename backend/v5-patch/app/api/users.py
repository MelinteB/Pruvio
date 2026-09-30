import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserDeletionConfirmRequest,
    UserDeletionOtpRequest,
    UserResponse,
)
from app.services.account_service import confirm_and_delete_account, request_account_deletion_otp
from app.services.user_service import create_user, get_user_by_phone, get_users

router = APIRouter()


def require_admin_api_key(x_pruvio_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("PRUVIO_ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API is not configured.")
    if x_pruvio_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin API key.")


@router.get("/", response_model=list[UserResponse], dependencies=[Depends(require_admin_api_key)])
def list_users(db: Session = Depends(get_db)):
    """Admin-only user list. Includes email when available."""
    return get_users(db)


@router.post("/", response_model=UserResponse, dependencies=[Depends(require_admin_api_key)])
def add_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = get_user_by_phone(db, user_data.phone_number)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    user = create_user(db, user_data)
    if user_data.email:
        user.email = str(user_data.email).lower()
        db.commit()
        db.refresh(user)
    return user


@router.post("/{user_id}/deletion/request-otp")
def request_deletion_otp(
    user_id: int,
    payload: UserDeletionOtpRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    try:
        result = request_account_deletion_otp(db, user, payload.channel)
        return {
            "user_id": user.id,
            "destination_type": result["destination_type"],
            "destination": result["destination"],
            "message": "Deletion verification code sent.",
            "debug_otp": result.get("debug_otp"),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    payload: UserDeletionConfirmRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    try:
        confirm_and_delete_account(db, user, payload.channel, payload.code)
        return {"deleted": True, "user_id": user_id}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
