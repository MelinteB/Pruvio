import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.verification_code import VerificationCode


def normalize_phone_number(phone_number: str) -> str:
    raw = (phone_number or "").strip()
    digits = re.sub(r"\D", "", raw)

    if not digits:
        raise ValueError("Phone number is required.")

    if raw.startswith("+"):
        return "+" + digits

    if digits.startswith("00"):
        return "+" + digits[2:]

    if digits.startswith("0") and len(digits) == 10:
        return "+40" + digits[1:]

    return "+" + digits


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None

    return email.strip().lower()


def get_otp_ttl_minutes() -> int:
    return int(os.getenv("OTP_CODE_TTL_MINUTES", "10"))


def get_otp_max_attempts() -> int:
    return int(os.getenv("OTP_MAX_ATTEMPTS", "5"))


def should_return_debug_code() -> bool:
    return os.getenv("OTP_DEBUG_RETURN_CODE", "false").lower() == "true"


def generate_otp_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


def hash_otp_code(destination: str, code: str) -> str:
    secret = os.getenv("OTP_SECRET", "dev-secret-change-me")
    value = f"{secret}:{destination}:{code}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def build_whatsapp_otp_delivery(phone_number: str, code: str) -> dict:
    return {
        "channel": "whatsapp",
        "status": "mock_ready",
        "to": phone_number,
        "template_name": "pruvio_otp_login",
        "message_to_send": (
            f"Your Pruvio verification code is {code}. "
            f"It expires in {get_otp_ttl_minutes()} minutes."
        )
    }


def build_email_otp_delivery(email: str, code: str) -> dict:
    return {
        "channel": "email",
        "status": "mock_ready",
        "to": email,
        "subject": "Your Pruvio verification code",
        "message_to_send": (
            f"Your Pruvio verification code is {code}. "
            f"It expires in {get_otp_ttl_minutes()} minutes."
        )
    }


def find_user_by_phone(
    db: Session,
    phone_number: str
) -> User | None:
    normalized_phone = normalize_phone_number(phone_number)

    return (
        db.query(User)
        .filter(User.phone_number == normalized_phone)
        .first()
    )


def find_user_by_email(
    db: Session,
    email: str
) -> User | None:
    normalized_email = normalize_email(email)

    return (
        db.query(User)
        .filter(User.email == normalized_email)
        .first()
    )


def create_or_update_pending_user(
    db: Session,
    phone_number: str,
    display_name: str | None = None,
    email: str | None = None,
    accepted_terms: bool = False
) -> User:
    normalized_phone = normalize_phone_number(phone_number)
    normalized_email = normalize_email(email)

    user = (
        db.query(User)
        .filter(User.phone_number == normalized_phone)
        .first()
    )

    if not user:
        user = User(
            phone_number=normalized_phone,
            name=display_name,
            email=normalized_email,
            status="pending_join",
            accepted_terms=accepted_terms,
            accepted_terms_at=datetime.utcnow() if accepted_terms else None,
            is_phone_verified=False,
            is_email_verified=False,
            last_seen_at=datetime.utcnow()
        )

        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    if display_name:
        user.name = display_name

    if normalized_email:
        user.email = normalized_email

    if accepted_terms:
        user.accepted_terms = True
        user.accepted_terms_at = datetime.utcnow()

    user.last_seen_at = datetime.utcnow()

    if user.status != "active":
        user.status = "pending_join"

    db.commit()
    db.refresh(user)

    return user


def expire_previous_codes(
    db: Session,
    user_id: int,
    destination_type: str,
    purpose: str = "onboarding"
):
    previous_codes = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.user_id == user_id,
            VerificationCode.destination_type == destination_type,
            VerificationCode.purpose == purpose,
            VerificationCode.status == "pending"
        )
        .all()
    )

    for previous_code in previous_codes:
        previous_code.status = "expired"

    db.commit()


def create_verification_code(
    db: Session,
    user: User,
    destination_type: str,
    destination: str,
    purpose: str = "onboarding"
) -> tuple[VerificationCode, str]:
    code = generate_otp_code()

    expire_previous_codes(
        db=db,
        user_id=user.id,
        destination_type=destination_type,
        purpose=purpose
    )

    verification_code = VerificationCode(
        user_id=user.id,
        destination_type=destination_type,
        destination=destination,
        purpose=purpose,
        code_hash=hash_otp_code(destination, code),
        status="pending",
        attempts=0,
        max_attempts=get_otp_max_attempts(),
        expires_at=datetime.utcnow() + timedelta(minutes=get_otp_ttl_minutes())
    )

    db.add(verification_code)
    db.commit()
    db.refresh(verification_code)

    return verification_code, code


def activate_user_if_ready(
    db: Session,
    user: User
):
    email_required = bool(user.email)

    can_activate = (
        bool(user.accepted_terms)
        and bool(user.is_phone_verified)
        and (
            not email_required
            or bool(user.is_email_verified)
        )
    )

    if can_activate:
        user.status = "active"
    else:
        user.status = "pending_join"

    user.last_seen_at = datetime.utcnow()

    db.commit()
    db.refresh(user)


def build_user_response(
    user: User,
    action: str,
    message: str,
    phone_delivery: dict | None = None,
    email_delivery: dict | None = None,
    debug_phone_otp: str | None = None,
    debug_email_otp: str | None = None
) -> dict:
    return {
        "user_id": user.id,
        "phone_number": user.phone_number,
        "email": user.email,
        "display_name": user.name,
        "status": user.status,
        "accepted_terms": bool(user.accepted_terms),
        "is_phone_verified": bool(user.is_phone_verified),
        "is_email_verified": bool(user.is_email_verified),
        "action": action,
        "message": message,
        "phone_delivery": phone_delivery,
        "email_delivery": email_delivery,
        "debug_phone_otp": debug_phone_otp if should_return_debug_code() else None,
        "debug_email_otp": debug_email_otp if should_return_debug_code() else None
    }


def start_otp_onboarding(
    db: Session,
    phone_number: str,
    display_name: str | None = None,
    email: str | None = None,
    accepted_terms: bool = False
) -> dict:
    if not accepted_terms:
        raise ValueError("Terms must be accepted before starting verification.")

    user = create_or_update_pending_user(
        db=db,
        phone_number=phone_number,
        display_name=display_name,
        email=email,
        accepted_terms=accepted_terms
    )

    phone_code_record, phone_code = create_verification_code(
        db=db,
        user=user,
        destination_type="phone",
        destination=user.phone_number
    )

    phone_delivery = build_whatsapp_otp_delivery(
        phone_number=user.phone_number,
        code=phone_code
    )

    email_delivery = None
    email_code = None

    if user.email:
        email_code_record, email_code = create_verification_code(
            db=db,
            user=user,
            destination_type="email",
            destination=user.email
        )

        email_delivery = build_email_otp_delivery(
            email=user.email,
            code=email_code
        )

    return build_user_response(
        user=user,
        action="otp_sent",
        message="Verification code sent. Complete OTP verification to activate your Pruvio account.",
        phone_delivery=phone_delivery,
        email_delivery=email_delivery,
        debug_phone_otp=phone_code,
        debug_email_otp=email_code
    )


def verify_code(
    db: Session,
    destination_type: str,
    destination: str,
    code: str
) -> User:
    normalized_destination = (
        normalize_phone_number(destination)
        if destination_type == "phone"
        else normalize_email(destination)
    )

    if not normalized_destination:
        raise ValueError("Verification destination is required.")

    verification_code = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.destination_type == destination_type,
            VerificationCode.destination == normalized_destination,
            VerificationCode.status == "pending"
        )
        .order_by(VerificationCode.created_at.desc())
        .first()
    )

    if not verification_code:
        raise ValueError("No active verification code found.")

    if verification_code.expires_at < datetime.utcnow():
        verification_code.status = "expired"
        db.commit()
        raise ValueError("Verification code expired.")

    if verification_code.attempts >= verification_code.max_attempts:
        verification_code.status = "failed"
        db.commit()
        raise ValueError("Maximum verification attempts exceeded.")

    verification_code.attempts += 1

    expected_hash = hash_otp_code(
        destination=normalized_destination,
        code=code.strip()
    )

    if verification_code.code_hash != expected_hash:
        db.commit()
        raise ValueError("Invalid verification code.")

    verification_code.status = "verified"
    verification_code.verified_at = datetime.utcnow()

    user = (
        db.query(User)
        .filter(User.id == verification_code.user_id)
        .first()
    )

    if not user:
        raise ValueError("User not found for verification code.")

    if destination_type == "phone":
        user.is_phone_verified = True

    if destination_type == "email":
        user.is_email_verified = True

    activate_user_if_ready(
        db=db,
        user=user
    )

    db.commit()
    db.refresh(user)

    return user


def verify_phone_otp(
    db: Session,
    phone_number: str,
    code: str
) -> dict:
    user = verify_code(
        db=db,
        destination_type="phone",
        destination=phone_number,
        code=code
    )

    if user.status == "active":
        message = "Phone verified. Your Pruvio account is now active."
    elif user.email and not user.is_email_verified:
        message = "Phone verified. Please verify your email to activate your Pruvio account."
    else:
        message = "Phone verified. Additional onboarding steps are required."

    return build_user_response(
        user=user,
        action="phone_verified",
        message=message
    )


def verify_email_otp(
    db: Session,
    email: str,
    code: str
) -> dict:
    user = verify_code(
        db=db,
        destination_type="email",
        destination=email,
        code=code
    )

    if user.status == "active":
        message = "Email verified. Your Pruvio account is now active."
    elif not user.is_phone_verified:
        message = "Email verified. Please verify your phone number to activate your Pruvio account."
    else:
        message = "Email verified. Additional onboarding steps are required."

    return build_user_response(
        user=user,
        action="email_verified",
        message=message
    )