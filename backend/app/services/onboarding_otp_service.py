import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.legal_content import PRIVACY_VERSION, TERMS_VERSION
from app.models.user import User
from app.models.verification_code import VerificationCode
from app.services.email_service import send_email_verification_code
from app.services.phone_otp_service import record_delivery
from app.services.username_service import check_username_available
from app.usernames import username_key
from app.services.trusted_device_service import is_trusted_device
from app.services.password_service import hash_password


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
    return db.query(User).filter(func.lower(User.email) == normalized).first()


def find_user_by_identifier(db: Session, identifier: str) -> User | None:
    value = (identifier or "").strip()
    if not value:
        return None
    if "@" in value:
        return find_user_by_email(db, value)
    try:
        key = username_key(value)
    except ValueError:
        return None
    return db.query(User).filter(User.username_key == key).first()


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
        row.code_ciphertext = None
    db.commit()


def create_verification_code(
    db: Session,
    user: User,
    destination_type: str,
    destination: str,
    purpose: str,
    *, context_value: str | None = None,
) -> tuple[VerificationCode, str]:
    if destination_type != "email":
        raise ValueError("Only email OTP is supported.")
    _assert_send_allowed(db, user, destination_type, purpose)
    expire_previous_codes(db, user.id, destination_type, purpose)
    code = generate_otp_code()
    row = VerificationCode(
        user_id=user.id,
        destination_type=destination_type,
        destination=destination,
        purpose=purpose,
        code_hash=hash_otp_code(destination, code),
        challenge_id=secrets.token_urlsafe(32),
        context_value=context_value,
        code_ciphertext=None,
        status="pending",
        attempts=0,
        max_attempts=get_otp_max_attempts(),
        expires_at=datetime.utcnow() + timedelta(minutes=get_otp_ttl_minutes()),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, code


def _deliver(destination_type: str, destination: str, code: str, *, db=None, row=None) -> dict:
    ttl = get_otp_ttl_minutes()
    if destination_type != "email":
        raise ValueError("Only email OTP is supported.")
    result = send_email_verification_code(destination, code, ttl)
    if db is not None and row is not None:
        record_delivery(db, row, result)
    return result


def _debug_code(code: str) -> str | None:
    return code if should_return_debug_code() else None


def create_or_update_registration_user(
    db: Session, *, phone_number: str, display_name: str, email: str,
    accepted_terms: bool, accepted_privacy: bool,
    username: str | None = None, marketing_opt_in: bool = False, password: str | None = None,
) -> User:
    phone = normalize_phone_number(phone_number)
    normalized_email = normalize_email(email)
    name = " ".join((display_name or "").split())
    if not name:
        raise ValueError("Full name is required.")
    if not normalized_email:
        raise ValueError("Email is required.")
    if not accepted_terms or not accepted_privacy:
        raise ValueError("You must review and accept the Terms and Privacy Notice before registration.")
    # Validate the password before storing any changes to a pending account.
    password_hash = hash_password(password) if password else None
    phone_owner = db.query(User).filter(User.phone_number == phone).first()
    email_owner = find_user_by_email(db, normalized_email)
    if phone_owner and email_owner and phone_owner.id != email_owner.id:
        raise ValueError("The phone number and email belong to different existing accounts.")
    user = email_owner or phone_owner
    if user and user.status == "active":
        raise ValueError("An account already exists. Use Sign in instead.")
    if user and user.status == "blocked":
        raise ValueError("This account is currently unavailable.")
    # An unverified phone is contact information, not proof that somebody owns an account.
    if phone_owner and phone_owner.email and normalize_email(phone_owner.email) != normalized_email:
        raise ValueError("This phone number is already used by another account.")
    clean_username = check_username_available(db, username or name, exclude_user_id=user.id if user else None)
    if not user:
        user = User(phone_number=phone)
        db.add(user)
    user.is_email_verified = False
    user.phone_number = phone
    user.is_phone_verified = False
    user.email = normalized_email
    user.name = name
    user.username = clean_username
    user.username_key = username_key(clean_username)
    user.status = "pending_join"
    user.accepted_terms = True
    user.accepted_terms_at = datetime.utcnow()
    user.terms_version = TERMS_VERSION
    user.accepted_privacy = True
    user.accepted_privacy_at = datetime.utcnow()
    user.privacy_version = PRIVACY_VERSION
    user.marketing_opt_in = bool(marketing_opt_in)
    if password_hash:
        user.password_hash = password_hash
    user.last_seen_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Username, email or phone number is already in use. Review your details.")
    db.refresh(user)
    return user


def start_registration(
    db: Session, *, phone_number: str, display_name: str, email: str,
    accepted_terms: bool, accepted_privacy: bool,
    username: str | None = None, marketing_opt_in: bool = False, password: str | None = None,
) -> dict:
    user = create_or_update_registration_user(
        db, phone_number=phone_number, display_name=display_name, email=email,
        username=username, accepted_terms=accepted_terms, accepted_privacy=accepted_privacy,
        marketing_opt_in=marketing_opt_in, password=password,
    )
    row, code = create_verification_code(db, user, "email", user.email, "registration")
    delivery = _deliver("email", user.email, code, db=db, row=row)
    return {"user": user, "challenge_id": row.challenge_id, "email_delivery": delivery,
            "debug_email_otp": _debug_code(code), "phone_delivery": None, "debug_phone_otp": None}


def verify_code(
    db: Session,
    *,
    destination_type: str,
    destination: str,
    code: str,
    purpose: str,
    challenge_id: str | None = None,
    user_id: int | None = None,
    context_value: str | None = None,
) -> User:
    if destination_type != "email":
        raise ValueError("Only email OTP is supported.")
    normalized = normalize_email(destination)
    if not normalized:
        raise ValueError("Verification destination is required.")

    if purpose == "login" and not challenge_id:
        raise ValueError("Request a code from this sign-in screen first.")
    row = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.challenge_id == challenge_id if challenge_id else True,
            VerificationCode.user_id == user_id if user_id is not None else True,
            VerificationCode.context_value == context_value if context_value is not None else True,
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
        row.code_ciphertext = None
        db.commit()
        raise ValueError("Verification code expired.")
    if row.attempts >= row.max_attempts:
        row.status = "failed"
        row.code_ciphertext = None
        db.commit()
        raise ValueError("Maximum verification attempts exceeded.")

    owner = db.get(User, row.user_id)
    if not owner or owner.status == "blocked":
        raise ValueError("This account is currently unavailable.")
    attempts = row.attempts
    expected = hash_otp_code(normalized, (code or "").strip())
    valid = hmac.compare_digest(row.code_hash, expected)
    now = datetime.utcnow()
    values = {"attempts": attempts + 1}
    if valid:
        values.update(status="verified", verified_at=now, code_ciphertext=None)
    elif attempts + 1 >= row.max_attempts:
        values.update(status="failed", code_ciphertext=None)
    changed = db.query(VerificationCode).filter(
        VerificationCode.id == row.id, VerificationCode.status == "pending",
        VerificationCode.attempts == attempts, VerificationCode.expires_at > now,
    ).update(values, synchronize_session=False)
    if changed != 1:
        db.rollback()
        raise ValueError("Verification code expired or already used. Request a new code.")
    if not valid:
        db.commit()
        raise ValueError("Invalid verification code.")
    db.refresh(row)
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise ValueError("User not found for verification code.")

    if purpose in {"registration", "login"}:
        # Only a code sent to the current account email may verify the account.
        if normalize_email(user.email) != normalized:
            db.rollback()
            raise ValueError("The account email changed. Request a new code.")
        user.is_email_verified = True
        if purpose == "registration" and user.accepted_terms and user.accepted_privacy:
            user.status = "active"
    user.last_seen_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def verify_registration_phone(db: Session, phone_number: str, code: str) -> User:
    raise ValueError("Phone verification is disabled. Verify your email instead.")


def verify_registration_email(db: Session, email: str, code: str, *, challenge_id: str | None = None) -> User:
    return verify_code(db, destination_type="email", destination=email, code=code,
                       purpose="registration", challenge_id=challenge_id)


def resend_registration_code(db: Session, user: User, destination_type: str = "email") -> dict:
    if destination_type != "email":
        raise ValueError("Only email OTP is supported.")
    if not user or user.status != "pending_join" or not user.email:
        raise ValueError("Registration session expired. Start again.")
    row, code = create_verification_code(db, user, "email", user.email, "registration")
    return {"challenge_id": row.challenge_id, "delivery": _deliver("email", user.email, code, db=db, row=row),
            "debug_otp": _debug_code(code)}


def send_login_otp(db: Session, identifier: str, *, device_token: str | None = None) -> dict:
    user = find_user_by_identifier(db, identifier)
    if not user or user.status != "active":
        raise ValueError("No active Pruvs account was found for these details.")
    if is_trusted_device(db, user, device_token):
        raise ValueError("This device is already verified. Sign in with password or passkey.")
    destination = normalize_email(user.email)
    if not destination:
        raise ValueError("This account needs an email address. Contact support.")
    row, code = create_verification_code(db, user, "email", destination, "login")
    return {"user": user, "challenge_id": row.challenge_id, "destination_type": "email",
            "destination": destination, "delivery": _deliver("email", destination, code, db=db, row=row),
            "debug_otp": _debug_code(code)}


def verify_login_otp(db: Session, identifier: str, code: str, *, challenge_id: str,
                     device_token: str | None = None) -> User:
    account = find_user_by_identifier(db, identifier)
    if not account or account.status != "active":
        raise ValueError("This account is not active.")
    if is_trusted_device(db, account, device_token):
        raise ValueError("This device is already verified. Sign in with password or passkey.")
    return verify_code(db, destination_type="email", destination=account.email, code=code,
                       purpose="login", challenge_id=challenge_id, user_id=account.id)


# Backward-compatible API wrappers

def start_otp_onboarding(
    db: Session,
    phone_number: str,
    display_name: str | None = None,
    email: str | None = None,
    accepted_terms: bool = False,
    accepted_privacy: bool = False,
    password: str | None = None,
    username: str | None = None,
) -> dict:
    result = start_registration(
        db,
        phone_number=phone_number,
        display_name=display_name or "Pruvs user",
        email=email or "",
        accepted_terms=accepted_terms,
        accepted_privacy=accepted_privacy,
        password=password,
        username=username,
    )
    user = result["user"]
    return {
        "user_id": user.id,
        "phone_number": user.phone_number,
        "email": user.email,
        "display_name": user.name,
        "username": user.username,
        "status": user.status,
        "accepted_terms": user.accepted_terms,
        "is_phone_verified": user.is_phone_verified,
        "is_email_verified": user.is_email_verified,
        "challenge_id": result["challenge_id"],
        "action": "otp_delivery_requested",
        "message": "Email verification delivery requested.",
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
        "username": user.username,
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


def verify_email_otp(db: Session, email: str, code: str, *, challenge_id: str) -> dict:
    user = verify_registration_email(db, email, code, challenge_id=challenge_id)
    return _legacy_response(user, "email_verified", "Email verified.")


def get_otp_onboarding_status(db: Session, identifier: str) -> dict:
    user = find_user_by_identifier(db, identifier)
    if not user:
        return {"user_id": None, "phone_number": "", "username": None, "email": None,
                "display_name": None, "status": "not_found", "accepted_terms": False,
                "is_phone_verified": False, "is_email_verified": False, "can_create_split_bill": False,
                "action": "not_found", "message": "User does not exist in Pruvs yet."}
    result = _legacy_response(user, "status", f"User status is {user.status}.")
    result["can_create_split_bill"] = user.status == "active" and user.is_email_verified
    return result
