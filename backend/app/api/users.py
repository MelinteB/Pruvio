import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.account_service import delete_user_completely, request_account_deletion_otp
from app.services.user_service import create_user, get_user_by_phone, get_users

router = APIRouter()


def require_admin_api_key(x_pruvio_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("PRUVIO_ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API is not configured.")
    if not x_pruvio_admin_key or not secrets.compare_digest(x_pruvio_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid admin API key.")


@router.get("/", response_model=list[UserResponse], dependencies=[Depends(require_admin_api_key)])
def list_users(db: Session = Depends(get_db)):
    """Admin-only user list. Email is included when available."""
    return get_users(db)


@router.post("/", response_model=UserResponse, dependencies=[Depends(require_admin_api_key)])
def add_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = get_user_by_phone(db, user_data.phone_number)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    try:
        user = create_user(db, user_data)
    except ValueError as error:
        raise HTTPException(400, detail=str(error))
    if user_data.email:
        user.email = str(user_data.email).lower()
        db.commit()
        db.refresh(user)
    return user


@router.delete("/{user_id}", dependencies=[Depends(require_admin_api_key)])
def delete_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """
    Permanently delete a user and the user's Pruvs data using the admin API key.

    This administrative operation intentionally does not require an OTP, an
    active account, or a verified email address. End-user account deletion from
    the Account UI continues to require email OTP confirmation.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        delete_user_completely(db, user)
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"User deletion failed: {error}")

    return {
        "deleted": True,
        "user_id": user_id,
        "verification_required": False,
    }


@router.post(
    "/{user_id}/deletion-otp",
    dependencies=[Depends(require_admin_api_key)],
    include_in_schema=False,
)
def request_deletion_otp(user_id: int, db: Session = Depends(get_db)):
    """Legacy endpoint retained for compatibility; admin deletion no longer uses OTP."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="User not found.")
    try:
        return request_account_deletion_otp(db, user, "email")
    except ValueError as error:
        raise HTTPException(400, detail=str(error))
