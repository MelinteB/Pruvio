from datetime import datetime
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate


def get_users(db: Session):
    return db.query(User).order_by(User.created_at.desc()).all()


def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_phone(db: Session, phone_number: str):
    return db.query(User).filter(User.phone_number == phone_number).first()


def create_user(db: Session, user_data: UserCreate):
    user = User(
        phone_number=user_data.phone_number,
        name=user_data.name,
        status="pending_join",
        accepted_terms=False,
        last_seen_at=datetime.utcnow()
    )

    db.add(user)
    db.commit()
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