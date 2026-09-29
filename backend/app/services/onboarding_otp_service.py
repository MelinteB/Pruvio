import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.legal_content import PRIVACY_VERSION, TERMS_VERSION
from app.models.user import User
from app.models.verification_code import VerificationCode
from app.services.email_service import send_email_verification_code
from app.services.sms_service import send_sms_verification_code


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


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
    value = (email or "").strip().lower()
    if not value:
        return None
    if not EMAIL_RE.fullmatch(value):
        raise ValueError("Enter a valid email address.")
    return value


def get_otp_ttl_minutes() -> int:
    return int(os.getenv("OTP_CODE_TTL_MINUTES", "10"))


def get_otp_max_attempts() -> int:
    return int(os.getenv("OTP_MAX_ATTEMPTS", "5"))


def get_otp_max_sends_per_hour() -> int:
    return int(os.getenv("OTP_MAX_SENDS_PER_HOUR", "5"))


def get_otp_resend_cooldown_seconds() -> int:
    return int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))


def should_return_debug_code() -> bool:
    return os.getenv("OTP_DEBUG_RETURN_CODE", "false").lower() == "true"


def generate_otp_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


def hash_otp_code(destination: str, code: str) -> str:
    secret = os.getenv("OTP_SECRET", "dev-secret-change-me")
    value = f"{secret}:{destination}:{code}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def find_user_by_phone(db: Session, phone_number: str) -> User | None:
    normalized = normalize_phone_number(phone_number)
    return db.query(User).filter(User.phone_number == normalized).first()


def find_user_by_email(db: Session, email: str) -> User | None:
    normalized = normalize_email(email)
    if not normalized:
        return None
    return db.query(User).filter(User.email == normalized).first()


def find_user_by_identifier(db: Session, identifier: str) -> User | None:
    value = (identifier or "").strip()
    if not value:
        return None
    if "@" in value:
        return find_user_by_email(db, value)
    return find_user_by_phone(db, value)


def _destination_for_identifier(identifier: str) -> tuple[str, str]:
    value = (identifier or "").strip()
    if "@" in value:
        email = normalize_email(value)
        if not email:
            raise ValueError("Enter a valid email address.")
        return "email", email
    return "phone", normalize_phone_number(value)


def _assert_send_allowed(db: Session, user: User, destination_type: str, purpose: str) -> None:
    now = datetime.utcnow()
    last = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.user_id == user.id,
            VerificationCode.destination_type == destination_type,
            VerificationCode.purpose == purpose,
        )
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    cooldown = get_otp_resend_cooldown_seconds()
    if last and last.created_at and (now - last.created_at).total_seconds() < cooldown:
        remaining = cooldown - int((now - last.created_at).total_seconds())
        raise ValueError(f"Please wait {max(1, remaining)} seconds before requesting another code.")

    hour_ago = now - timedelta(hours=1)
    sent_count = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.user_id == user.id,
            VerificationCode.destination_type == destination_type,
            VerificationCode.purpose == purpose,
            VerificationCode.created_at >= hour_ago,
        )
        .count()
    )
    if sent_count >= get_otp_max_sends_per_hour():
        raise ValueError("Too many verification codes requested. Please try again later.")


def expire_previous_codes(db: Session, user_id: int, destination_type: str, purpose: str) -> None:
    rows = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.user_id == user_id,
            VerificationCode.destination_type == destination_type,
            VerificationCode.purpose == purpose,
            VerificationCode.status == "pending",
        )
        .all()
    )
    for row in rows:
        row.status = "expired"
    db.commit()


def create_verification_code(
    db: Session,
    user: User,
    destination_type: str,
    destination: str,
    purpose: str,
) -> tuple[VerificationCode, str]:
    _assert_send_allowed(db, user, destination_type, purpose)
    expire_previous_codes(db, user.id, destination_type, purpose)
    code = generate_otp_code()
    row = VerificationCode(
        user_id=user.id,
        destination_type=destination_type,
        destination=destination,
        purpose=purpose,
        code_hash=hash_otp_code(destination, code),
        status="pending",
        attempts=0,
        max_attempts=get_otp_max_attempts(),
        expires_at=datetime.utcnow() + timedelta(minutes=get_otp_ttl_minutes()),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, code


def _deliver(destination_type: str, destination: str, code: str) -> dict:
    ttl = get_otp_ttl_minutes()
    if destination_type == "email":
        return send_email_verification_code(destination, code, ttl)
    return send_sms_verification_code(destination, code, ttl)


def _debug_code(code: str) -> str | None:
    return code if should_return_debug_code() else None


def create_or_update_registration_user(
    db: Session,
    *,
    phone_number: str,
    display_name: str,
    email: str,
    accepted_terms: bool,
    accepted_privacy: bool,
    marketing_opt_in: bool = False,
) -> User:
    phone = normalize_phone_number(phone_number)
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise ValueError("Email is required.")
    name = (display_name or "").strip()
    if not name:
        raise ValueError("Name is required.")
    if not accepted_terms or not accepted_privacy:
        raise ValueError("You must review and accept the Terms and Privacy Notice before registration.")

    phone_owner = db.query(User).filter(User.phone_number == phone).first()
    email_owner = db.query(User).filter(User.email == normalized_email).first()

    if phone_owner and email_owner and phone_owner.id != email_owner.id:
        raise ValueError("The phone number and email belong to different existing accounts.")

    user = phone_owner or email_owner
    if user and user.status == "active":
        raise ValueError("An account already exists. Use Sign in instead.")

    if not user:
        user = User(phone_number=phone)
        db.add(user)

    if email_owner and email_owner.id != user.id:
        raise ValueError("This email is already registered.")
    if phone_owner and phone_owner.id != user.id:
        raise ValueError("This phone number is already registered.")

    user.phone_number = phone
    user.email = normalized_email
    user.name = name
    user.status = "pending_join"
    user.accepted_terms = True
    user.accepted_terms_at = datetime.utcnow()
    user.terms_version = TERMS_VERSION
    user.accepted_privacy = True
    user.accepted_privacy_at = datetime.utcnow()
    user.privacy_version = PRIVACY_VERSION
    user.marketing_opt_in = bool(marketing_opt_in)
    user.last_seen_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def start_registration(
    db: Session,
    *,
    phone_number: str,
    display_name: str,
    email: str,
    accepted_terms: bool,
    accepted_privacy: bool,
    marketing_opt_in: bool = False,
) -> dict:
    user = create_or_update_registration_user(
        db,
        phone_number=phone_number,
        display_name=display_name,
        email=email,
        accepted_terms=accepted_terms,
        accepted_privacy=accepted_privacy,
        marketing_opt_in=marketing_opt_in,
    )

    _, phone_code = create_verification_code(db, user, "phone", user.phone_number, "registration")
    _, email_code = create_verification_code(db, user, "email", user.email, "registration")
    phone_delivery = _deliver("phone", user.phone_number, phone_code)
    email_delivery = _deliver("email", user.email, email_code)

    return {
        "user": user,
        "phone_delivery": phone_delivery,
        "email_delivery": email_delivery,
        "debug_phone_otp": _debug_code(phone_code),
        "debug_email_otp": _debug_code(email_code),
    }


def verify_code(
    db: Session,
    *,
    destination_type: str,
    destination: str,
    code: str,
    purpose: str,
) -> User:
    normalized = normalize_email(destination) if destination_type == "email" else normalize_phone_number(destination)
    if not normalized:
        raise ValueError("Verification destination is required.")

    row = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.destination_type == destination_type,
            VerificationCode.destination == normalized,
            VerificationCode.purpose == purpose,
            VerificationCode.status == "pending",
        )
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if not row:
        raise ValueError("No active verification code found.")
    if row.expires_at < datetime.utcnow():
        row.status = "expired"
        db.commit()
        raise ValueError("Verification code expired.")
    if row.attempts >= row.max_attempts:
        row.status = "failed"
        db.commit()
        raise ValueError("Maximum verification attempts exceeded.")

    row.attempts += 1
    expected = hash_otp_code(normalized, (code or "").strip())
    if not hmac.compare_digest(row.code_hash, expected):
        db.commit()
        raise ValueError("Invalid verification code.")

    row.status = "verified"
    row.verified_at = datetime.utcnow()
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise ValueError("User not found for verification code.")

    if purpose == "registration":
        if destination_type == "phone":
            user.is_phone_verified = True
        else:
            user.is_email_verified = True
        if (
            user.accepted_terms
            and user.accepted_privacy
            and user.is_phone_verified
            and user.is_email_verified
        ):
            user.status = "active"
    user.last_seen_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def verify_registration_phone(db: Session, phone_number: str, code: str) -> User:
    return verify_code(
        db,
        destination_type="phone",
        destination=phone_number,
        code=code,
        purpose="registration",
    )


def verify_registration_email(db: Session, email: str, code: str) -> User:
    return verify_code(
        db,
        destination_type="email",
        destination=email,
        code=code,
        purpose="registration",
    )


def resend_registration_code(db: Session, user: User, destination_type: str) -> dict:
    if destination_type not in {"phone", "email"}:
        raise ValueError("Unsupported verification channel.")
    destination = user.phone_number if destination_type == "phone" else user.email
    if not destination:
        raise ValueError("Verification destination is missing.")
    _, code = create_verification_code(db, user, destination_type, destination, "registration")
    return {
        "delivery": _deliver(destination_type, destination, code),
        "debug_otp": _debug_code(code),
    }


def send_login_otp(db: Session, identifier: str) -> dict:
    user = find_user_by_identifier(db, identifier)
    if not user or user.status != "active":
        raise ValueError("No active Pruvio account was found for these details.")
    destination_type, destination = _destination_for_identifier(identifier)
    if destination_type == "email" and not user.is_email_verified:
        raise ValueError("This email address is not verified.")
    if destination_type == "phone" and not user.is_phone_verified:
        raise ValueError("This phone number is not verified.")

    _, code = create_verification_code(db, user, destination_type, destination, "login")
    delivery = _deliver(destination_type, destination, code)
    return {
        "user": user,
        "destination_type": destination_type,
        "destination": destination,
        "delivery": delivery,
        "debug_otp": _debug_code(code),
    }


def verify_login_otp(db: Session, identifier: str, code: str) -> User:
    destination_type, destination = _destination_for_identifier(identifier)
    user = verify_code(
        db,
        destination_type=destination_type,
        destination=destination,
        code=code,
        purpose="login",
    )
    if user.status != "active":
        raise ValueError("This account is not active.")
    return user


# Backward-compatible API wrappers

def start_otp_onboarding(
    db: Session,
    phone_number: str,
    display_name: str | None = None,
    email: str | None = None,
    accepted_terms: bool = False,
    accepted_privacy: bool = False,
) -> dict:
    result = start_registration(
        db,
        phone_number=phone_number,
        display_name=display_name or "Pruvio user",
        email=email or "",
        accepted_terms=accepted_terms,
        accepted_privacy=accepted_privacy,
    )
    user = result["user"]
    return {
        "user_id": user.id,
        "phone_number": user.phone_number,
        "email": user.email,
        "display_name": user.name,
        "status": user.status,
        "accepted_terms": user.accepted_terms,
        "is_phone_verified": user.is_phone_verified,
        "is_email_verified": user.is_email_verified,
        "action": "otp_sent",
        "message": "Verification codes sent.",
        "phone_delivery": result["phone_delivery"],
        "email_delivery": result["email_delivery"],
        "debug_phone_otp": result["debug_phone_otp"],
        "debug_email_otp": result["debug_email_otp"],
    }


def _legacy_response(user: User, action: str, message: str) -> dict:
    return {
        "user_id": user.id,
        "phone_number": user.phone_number,
        "email": user.email,
        "display_name": user.name,
        "status": user.status,
        "accepted_terms": user.accepted_terms,
        "is_phone_verified": user.is_phone_verified,
        "is_email_verified": user.is_email_verified,
        "action": action,
        "message": message,
        "phone_delivery": None,
        "email_delivery": None,
        "debug_phone_otp": None,
        "debug_email_otp": None,
    }


def verify_phone_otp(db: Session, phone_number: str, code: str) -> dict:
    user = verify_registration_phone(db, phone_number, code)
    return _legacy_response(user, "phone_verified", "Phone verified.")


def verify_email_otp(db: Session, email: str, code: str) -> dict:
    user = verify_registration_email(db, email, code)
    return _legacy_response(user, "email_verified", "Email verified.")


def get_otp_onboarding_status(db: Session, phone_number: str) -> dict:
    phone = normalize_phone_number(phone_number)
    user = db.query(User).filter(User.phone_number == phone).first()
    if not user:
        return {
            "user_id": None,
            "phone_number": phone,
            "email": None,
            "display_name": None,
            "status": "not_found",
            "accepted_terms": False,
            "is_phone_verified": False,
            "is_email_verified": False,
            "can_create_split_bill": False,
            "action": "not_found",
            "message": "User does not exist in Pruvio yet.",
        }
    return {
        "user_id": user.id,
        "phone_number": user.phone_number,
        "email": user.email,
        "display_name": user.name,
        "status": user.status,
        "accepted_terms": user.accepted_terms,
        "is_phone_verified": user.is_phone_verified,
        "is_email_verified": user.is_email_verified,
        "can_create_split_bill": user.status == "active",
        "action": "status",
        "message": f"User status is {user.status}.",
    }
