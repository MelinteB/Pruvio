"""Opt-in, OTP-verified merchant self-enrollment for Pruvs Business.

New merchants remain PENDING REVIEW and cannot authenticate until an operator
reviews their business registration. Resend is an email transport, not an OTP
validator. Keep this feature disabled in production pending legal/security review.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base, get_db
from .models import Merchant, Staff

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/merchant/enrollment", tags=["Merchant enrollment"])
PASSWORD_HASHER = PasswordHasher()
def UTC() -> datetime:
    # Repository uses naive UTC; avoid deprecated datetime.utcnow().
    return datetime.now(timezone.utc).replace(tzinfo=None)
OTP_TTL = timedelta(minutes=10)
OTP_COOLDOWN = timedelta(seconds=60)
MAX_OTP_SENDS = 5
MAX_OTP_ATTEMPTS = 5


class MerchantSignup(Base):
    __tablename__ = "merchant_signups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    owner_password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile: Mapped[dict] = mapped_column("profile_json", JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting_email")
    otp_hash: Mapped[str | None] = mapped_column(String(64))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    otp_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    otp_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    otp_sends: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    otp_window_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    merchant_id: Mapped[str | None] = mapped_column(String(80))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=UTC)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=UTC, onupdate=UTC)


class MerchantLegalProfile(Base):
    __tablename__ = "merchant_legal_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    profile: Mapped[dict] = mapped_column("profile_json", JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=UTC)


class MerchantSignupRate(Base):
    __tablename__ = "merchant_signup_rates"
    bucket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


class SignupData(BaseModel):
    legal_name: str = Field(min_length=2, max_length=180)
    trade_name: str = Field(min_length=2, max_length=180)
    tax_id: str = Field(min_length=2, max_length=20)
    registry_number: str = Field(min_length=4, max_length=50)
    caen_code: str = Field(min_length=4, max_length=8)
    vat_registered: bool = False
    registered_address: str = Field(min_length=6, max_length=300)
    city: str = Field(min_length=2, max_length=100)
    county: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=4, max_length=12)
    country: str = "RO"
    business_email: str = Field(min_length=5, max_length=255)
    business_phone: str = Field(min_length=6, max_length=30)
    website: str = Field(default="", max_length=255)
    category: str = Field(min_length=2, max_length=80)
    first_location_name: str = Field(min_length=2, max_length=180)
    first_location_address: str = Field(min_length=6, max_length=300)
    first_location_city: str = Field(min_length=2, max_length=100)
    pos_provider: str = Field(default="none", max_length=80)
    owner_full_name: str = Field(min_length=3, max_length=180)
    owner_email: str = Field(min_length=5, max_length=255)
    owner_phone: str = Field(min_length=6, max_length=30)
    owner_position: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=20, max_length=256)
    accept_terms: bool
    acknowledge_privacy: bool
    marketing_opt_in: bool = False

    @field_validator("owner_email", "business_email")
    @classmethod
    def email_format(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Invalid email address")
        return value

    @field_validator("country")
    @classmethod
    def country_ro(cls, value: str) -> str:
        if value.upper() != "RO":
            raise ValueError("Only Romanian legal entities are supported in this pilot")
        return "RO"

    @field_validator("tax_id")
    @classmethod
    def tax_id_ro(cls, value: str) -> str:
        value = re.sub(r"\s", "", value).upper()
        if not re.fullmatch(r"(?:RO)?\d{2,10}", value):
            raise ValueError("Provide a Romanian CUI/CIF")
        return value

    @field_validator("caen_code")
    @classmethod
    def caen_ro(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"\d{4}", value):
            raise ValueError("Provide the four-digit CAEN code")
        return value


class SignupSession(BaseModel):
    signup_id: str = Field(min_length=36, max_length=36)
    session_token: str = Field(min_length=32, max_length=128)


class VerifyCode(SignupSession):
    code: str = Field(pattern=r"^[0-9]{6}$")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def otp_digest(secret: str, signup_id: str, code: str) -> str:
    return hmac.new(secret.encode(), f"{signup_id}:{code}".encode(), hashlib.sha256).hexdigest()


def otp_secret() -> str:
    secret = os.getenv("PRUVS_BUSINESS_OTP_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Enrollment verification is not configured")
    return secret


def require_enabled() -> None:
    if os.getenv("PRUVS_BUSINESS_MERCHANT_SIGNUP_ENABLED", "false").lower() != "true":
        raise HTTPException(404, "Not found")
    otp_secret()
    if not os.getenv("RESEND_API_KEY") or not os.getenv("RESEND_FROM_EMAIL"):
        raise HTTPException(503, "Enrollment email service is not configured")


def enforce_limit(db: Session, key: str, *, max_attempts: int, minutes: int = 60) -> None:
    """Database-persisted limiter. Hash buckets so raw email/IP is not stored."""
    bucket = sha256(otp_secret() + ":" + key)
    now = UTC()
    row = db.execute(select(MerchantSignupRate).where(
        MerchantSignupRate.bucket_hash == bucket
    ).with_for_update()).scalar_one_or_none()
    if row is None:
        db.add(MerchantSignupRate(bucket_hash=bucket, window_started_at=now, attempts=1))
    elif row.window_started_at + timedelta(minutes=minutes) <= now:
        row.window_started_at, row.attempts = now, 1
    elif row.attempts >= max_attempts:
        raise HTTPException(429, "Too many requests; try again later")
    else:
        row.attempts += 1


def resend_failure_category(exc: HTTPError) -> str:
    """Classify provider/edge errors without logging recipient, OTP or response body."""
    try:
        content = exc.read(2048).decode("utf-8", errors="replace")
    except (OSError, UnicodeError):
        return "unreadable_response"
    # Some upstream bot filters reject Python-urllib before the provider API.
    if re.search(r"error code\s*:\s*1010\b", content, re.IGNORECASE):
        return "edge_1010"
    try:
        problem = json.loads(content)
    except (ValueError, TypeError):
        return "non_json_response"
    if isinstance(problem, dict):
        name = problem.get("name", "")
        if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", name):
            return "resend_" + name
    return "unclassified_response"


def send_resend_otp(email: str, code: str, signup_id: str, iteration: int) -> None:
    """Send with Resend's REST API; never log message body, code or credentials."""
    content = ("Your Pruvs Business verification code is " + code
               + ". It expires in 10 minutes. If you did not request it, ignore this email.")
    sender = os.environ["RESEND_FROM_EMAIL"]
    payload = {
        "from": sender,
        "to": [email],
        "subject": "Pruvs Business — verify your merchant email",
        "text": content,
        "html": (
            '<div style="font-family:Arial,sans-serif;max-width:480px">'
            '<h2>Pruvs Business</h2><p>Verify your merchant email address.</p>'
            f'<p style="font-size:30px;letter-spacing:8px;font-weight:bold">{html.escape(code)}</p>'
            '<p>This code expires in 10 minutes. Do not share it.</p>'
            '<p>If you did not request this, ignore this email.</p></div>'
        ),
    }
    headers = {
        "Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
        "Content-Type": "application/json",
        "Accept": "application/json",
        # urllib's default User-Agent can be rejected at an upstream edge before
        # Resend sees the request. Identify this application explicitly.
        "User-Agent": "PruvsBusiness/0.6.3 (+merchant-otp)",
        "Idempotency-Key": f"merchant-enroll-{signup_id}-{iteration}",
    }
    req = UrlRequest("https://api.resend.com/emails", data=json.dumps(payload).encode(),
                     headers=headers, method="POST")
    try:
        with urlopen(req, timeout=12) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError("Unexpected email provider status")
    except (HTTPError, URLError, OSError, RuntimeError) as exc:
        if isinstance(exc, HTTPError):
            logger.warning("Resend merchant OTP failed (http_status=%s, category=%s)",
                           exc.code, resend_failure_category(exc))
        else:
            logger.warning("Resend merchant OTP delivery failed (type=%s)", type(exc).__name__)
        raise HTTPException(503, "Verification email unavailable; try again") from None


def signup_record(db: Session, payload: SignupSession, *, lock: bool = True) -> MerchantSignup:
    query = select(MerchantSignup).where(MerchantSignup.id == payload.signup_id)
    if lock:
        query = query.with_for_update()
    row = db.execute(query).scalar_one_or_none()
    if not row or not secrets.compare_digest(row.session_hash, sha256(payload.session_token)):
        raise HTTPException(404, "Registration session not found")
    return row


@router.post("/start", status_code=202)
def start_enrollment(data: SignupData, request: Request, db: Session = Depends(get_db)):
    require_enabled()
    if not data.accept_terms or not data.acknowledge_privacy:
        raise HTTPException(422, "Merchant terms and privacy acknowledgement required")
    email = data.owner_email
    signup_id = str(uuid.uuid4())
    session_token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = UTC()
    with db.begin():
        ip = request.client.host if request.client else "unknown"
        enforce_limit(db, "begin-ip:" + ip, max_attempts=8)
        enforce_limit(db, "begin-email:" + email, max_attempts=4)
        if db.scalar(select(Staff.id).where(Staff.email == email)) is not None:
            raise HTTPException(409, "This address is unavailable for registration")
        if db.scalar(select(MerchantSignup.id).where(MerchantSignup.owner_email == email)):
            raise HTTPException(409, "Registration already exists; use your existing verification session")
        profile = data.model_dump(exclude={"password", "accept_terms", "acknowledge_privacy"})
        profile["terms_accepted_at"] = now.isoformat() + "Z"
        profile["privacy_acknowledged_at"] = now.isoformat() + "Z"
        profile["terms_version"] = "merchant-staging-v1"  # Replace with approved legal version before prod.
        profile["privacy_version"] = "merchant-staging-v1"
        row = MerchantSignup(
            id=signup_id, owner_email=email,
            owner_password_hash=PASSWORD_HASHER.hash(data.password),
            session_hash=sha256(session_token), profile=profile,
            status="awaiting_email", otp_hash=otp_digest(otp_secret(), signup_id, code),
            otp_expires_at=now + OTP_TTL, otp_last_sent_at=now,
            otp_attempts=0, otp_sends=1, otp_window_started_at=now,
        )
        db.add(row)
        db.flush()
        # If Resend rejects the send, the transaction rolls back; no locked draft remains.
        send_resend_otp(email, code, signup_id, 1)
    return {"signup_id": signup_id, "session_token": session_token,
            "email_masked": mask_email(email), "status": "awaiting_email",
            "expires_in_seconds": 600, "resend_after_seconds": 60}


def mask_email(email: str) -> str:
    user, _, domain = email.partition("@")
    return user[:1] + "***@" + domain


@router.post("/resend")
def resend_otp(payload: SignupSession, db: Session = Depends(get_db)):
    require_enabled()
    now = UTC()
    with db.begin():
        row = signup_record(db, payload)
        if row.status != "awaiting_email":
            raise HTTPException(409, "Registration is no longer awaiting verification")
        if row.otp_last_sent_at and now < row.otp_last_sent_at + OTP_COOLDOWN:
            raise HTTPException(429, "Please wait before requesting another code")
        if not row.otp_window_started_at or now >= row.otp_window_started_at + timedelta(hours=1):
            row.otp_window_started_at = now
            row.otp_sends = 0
        if row.otp_sends >= MAX_OTP_SENDS:
            raise HTTPException(429, "Too many codes requested; try again later")
        code = f"{secrets.randbelow(1_000_000):06d}"
        iteration = row.otp_sends + 1
        send_resend_otp(row.owner_email, code, row.id, int(now.timestamp()))
        row.otp_hash = otp_digest(otp_secret(), row.id, code)
        row.otp_expires_at = now + OTP_TTL
        row.otp_last_sent_at = now
        row.otp_sends = iteration
        row.otp_attempts = 0
    return {"status": "sent", "expires_in_seconds": 600, "resend_after_seconds": 60}


@router.post("/verify")
def verify_otp(payload: VerifyCode, db: Session = Depends(get_db)):
    require_enabled()
    now = UTC()
    with db.begin():
        row = signup_record(db, payload)
        if row.status != "awaiting_email":
            raise HTTPException(409, "Registration already verified or closed")
        if not row.otp_hash or not row.otp_expires_at or now > row.otp_expires_at:
            raise HTTPException(410, "Code expired; request a new one")
        if row.otp_attempts >= MAX_OTP_ATTEMPTS:
            raise HTTPException(429, "Too many attempts; request a new code")
        # Persist wrong attempts rather than rolling back HTTPException within transaction.
        if not secrets.compare_digest(row.otp_hash, otp_digest(otp_secret(), row.id, payload.code)):
            row.otp_attempts += 1
            wrong = True
        else:
            wrong = False
            if db.scalar(select(Staff.id).where(Staff.email == row.owner_email)) is not None:
                raise HTTPException(409, "Registration address already used")
            details = row.profile
            merchant = Merchant(name=details["trade_name"], status="pending")
            db.add(merchant)
            db.flush()
            staff = Staff(
                merchant_id=merchant.id, email=row.owner_email,
                password_hash=row.owner_password_hash, role="owner", active=False,
            )
            db.add(staff)
            db.add(MerchantLegalProfile(
                id=str(uuid.uuid4()), merchant_id=str(merchant.id),
                profile=details, review_status="pending_review",
            ))
            row.merchant_id = str(merchant.id)
            row.status = "pending_review"
            row.email_verified_at = now
            row.otp_hash = None
            row.otp_expires_at = None
    if wrong:
        raise HTTPException(400, "Incorrect verification code")
    return {"status": "pending_review", "merchant_id": row.merchant_id,
            "message": "Email verified. Merchant review pending."}


@router.post("/status")
def status(payload: SignupSession, db: Session = Depends(get_db)):
    require_enabled()
    row = signup_record(db, payload, lock=False)
    return {"status": row.status, "merchant_id": row.merchant_id if row.email_verified_at else None,
            "email_masked": mask_email(row.owner_email)}


@router.post("/cancel")
def cancel(payload: SignupSession, db: Session = Depends(get_db)):
    require_enabled()
    with db.begin():
        row = signup_record(db, payload)
        if row.status != "awaiting_email":
            raise HTTPException(409, "Verified registration cannot be canceled here")
        db.delete(row)
    return {"status": "canceled"}
