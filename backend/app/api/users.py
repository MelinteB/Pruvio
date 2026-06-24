from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import (
    get_users,
    get_user_by_phone,
    create_user
)

router = APIRouter()


@router.get("/", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)):
    return get_users(db)


@router.post("/", response_model=UserResponse)
def add_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = get_user_by_phone(db, user_data.phone_number)

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="User already exists"
        )

    return create_user(db, user_data)