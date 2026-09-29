from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.onboarding_otp_service import (
    find_user_by_identifier,
    send_login_otp,
    verify_login_otp,
)


def start_passwordless_login(db: Session, identifier: str) -> dict:
    return send_login_otp(db, identifier)


def complete_passwordless_login(db: Session, identifier: str, code: str) -> User:
    user = verify_login_otp(db, identifier, code)
    if user.status == "blocked":
        raise ValueError("This account is currently unavailable.")
    user.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def get_account_for_identifier(db: Session, identifier: str) -> User | None:
    return find_user_by_identifier(db, identifier)
