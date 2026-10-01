from datetime import datetime
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate
from app.services.username_service import check_username_available
from app.usernames import username_key
from sqlalchemy.exc import IntegrityError


def get_users(db: Session):
    return db.query(User).order_by(User.created_at.desc()).all()


def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_phone(db: Session, phone_number: str):
    return db.query(User).filter(User.phone_number == phone_number).first()


def create_user(db: Session, user_data: UserCreate):
    chosen = check_username_available(db, user_data.username or user_data.name or "User " + user_data.phone_number[-8:])
    user = User(
        username=chosen, username_key=username_key(chosen),
        phone_number=user_data.phone_number,
        name=user_data.name,
        status="pending_join",
        accepted_terms=False,
        last_seen_at=datetime.utcnow()
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Username or phone number is already in use.")
    db.refresh(user)

    return user


def activate_user(db: Session, user: User):
    user.status = "active"
    user.accepted_terms = True
    user.accepted_terms_at = datetime.utcnow()
    user.last_seen_at = datetime.utcnow()

    db.commit()
    db.refresh(user)

    return user


def block_user(db: Session, user: User):
    user.status = "blocked"
    user.accepted_terms = False
    user.last_seen_at = datetime.utcnow()

    db.commit()
    db.refresh(user)

    return user