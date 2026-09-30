import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.services.account_service import delete_user_completely
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
    user = create_user(db, user_data)
    if user_data.email:
        user.email = str(user_data.email).lower()
        db.commit()
        db.refresh(user)
    return user


@router.delete("/{user_id}", dependencies=[Depends(require_admin_api_key)])
def delete_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """Permanently delete a user and associated Pruvio data using the admin key."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    delete_user_completely(db, user)
    return {"deleted": True, "user_id": user_id}
