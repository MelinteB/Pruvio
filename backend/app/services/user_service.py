from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserAdminUpdate, UserCreate
from app.services.onboarding_otp_service import normalize_email, normalize_phone_number
from app.services.username_service import check_username_available
from app.usernames import normalize_username, username_key


def get_users(db: Session):
    return db.query(User).order_by(User.created_at.desc()).all()


def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_phone(db: Session, phone_number: str):
    return db.query(User).filter(User.phone_number == phone_number).first()


def create_user(db: Session, user_data: UserCreate):
    chosen = check_username_available(
        db,
        user_data.username or user_data.name or "User " + user_data.phone_number[-8:],
    )
    user = User(
        username=chosen,
        username_key=username_key(chosen),
        phone_number=user_data.phone_number,
        name=user_data.name,
        status="pending_join",
        is_admin=bool(getattr(user_data, "is_admin", False)),
        accepted_terms=False,
        last_seen_at=datetime.utcnow(),
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Username or phone number is already in use.")
    db.refresh(user)

    return user


def update_user_admin(db: Session, user: User, payload: UserAdminUpdate) -> User:
    """Update an existing user from the admin API without OTP requirements."""
    data = payload.model_dump(exclude_unset=True)
    explicit_fields = set(payload.model_fields_set)

    if not data:
        return user

    if "is_admin" in data:
        if data["is_admin"] is None:
            raise ValueError("Administrator role cannot be null.")
        user.is_admin = data["is_admin"]

    if "username" in data:
        value = data["username"]
        if value is None:
            raise ValueError("Username cannot be cleared.")

        normalized_username = normalize_username(value)
        requested_key = username_key(normalized_username)
        current_key = (
            user.username_key
            or username_key(user.username)
        )

        # PATCH must be idempotent: sending the user's existing username
        # must not trigger a uniqueness conflict.
        if requested_key != current_key:
            normalized_username = check_username_available(
                db,
                normalized_username,
                exclude_user_id=user.id,
            )

        user.username = normalized_username
        user.username_key = requested_key

    if "phone_number" in data:
        value = data["phone_number"]
        if value is None:
            raise ValueError("Phone number cannot be cleared.")
        normalized_phone = normalize_phone_number(value)

        if normalized_phone != user.phone_number:
            existing = (
                db.query(User.id)
                .filter(User.phone_number == normalized_phone, User.id != user.id)
                .first()
            )
            if existing:
                raise ValueError("Phone number is already in use.")

            user.phone_number = normalized_phone
            if "is_phone_verified" not in explicit_fields:
                user.is_phone_verified = False

    if "email" in data:
        normalized_email = normalize_email(data["email"])
        current_email = (user.email or "").strip().lower() or None

        if normalized_email != current_email:
            if normalized_email:
                existing = (
                    db.query(User.id)
                    .filter(func.lower(User.email) == normalized_email, User.id != user.id)
                    .first()
                )
                if existing:
                    raise ValueError("Email address is already in use.")

            user.email = normalized_email
            if "is_email_verified" not in explicit_fields:
                user.is_email_verified = False

    if "name" in data:
        user.name = (data["name"] or "").strip() or None

    if "status" in data and data["status"] is not None:
        user.status = data["status"]

    if "is_phone_verified" in data and data["is_phone_verified"] is not None:
        user.is_phone_verified = data["is_phone_verified"]

    if "is_email_verified" in data and data["is_email_verified"] is not None:
        user.is_email_verified = data["is_email_verified"]

    if "preferred_language" in data:
        value = data["preferred_language"]
        if value is None:
            raise ValueError("Preferred language cannot be cleared.")
        user.preferred_language = value.strip().lower()

    if "marketing_opt_in" in data and data["marketing_opt_in"] is not None:
        user.marketing_opt_in = data["marketing_opt_in"]

    if "notifications_opt_in" in data and data["notifications_opt_in"] is not None:
        user.notifications_opt_in = data["notifications_opt_in"]

    nullable_text_fields = (
        "revolut_payment_link",
        "payment_recipient_name",
        "payment_iban",
        "payment_bank_name",
        "payment_bic",
        "payment_note",
    )
    for field_name in nullable_text_fields:
        if field_name in data:
            value = data[field_name]
            setattr(user, field_name, (value or "").strip() or None)

    user.updated_at = datetime.utcnow()

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ValueError("Username, phone number, or another unique value is already in use.") from error

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
