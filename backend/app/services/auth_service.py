from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.onboarding_otp_service import (
    find_user_by_identifier,
    send_login_otp,
    verify_login_otp,
)
from app.services.password_service import verify_password


def start_passwordless_login(db: Session, identifier: str, *, device_token: str | None = None) -> dict:
    return send_login_otp(db, identifier, device_token=device_token)


def complete_passwordless_login(db: Session, identifier: str, code: str, *, challenge_id: str,
                                device_token: str | None = None) -> User:
    user = verify_login_otp(db, identifier, code, challenge_id=challenge_id, device_token=device_token)
    if user.status == "blocked":
        raise ValueError("This account is currently unavailable.")
    user.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def authenticate_with_password(db: Session, identifier: str, password: str) -> User:
    user = find_user_by_identifier(db, identifier)
    if not user or user.status != "active":
        raise ValueError("Invalid sign-in details.")
    if not verify_password(password or "", user.password_hash):
        raise ValueError("Invalid sign-in details.")
    user.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def get_account_for_identifier(db: Session, identifier: str) -> User | None:
    return find_user_by_identifier(db, identifier)
