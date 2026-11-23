"""Merchant password recovery with short-lived, password-bound signed reset links.

Disabled until the operator configures a verified Resend sender and enables the
feature. Links use URL fragments so reset tokens are never sent in GET requests.
No reset token, email address or account existence is exposed by the request API.
"""
from __future__ import annotations

import hashlib
import html
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
import json

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .merchant_enrollment import MerchantSignupRate, enforce_limit
from .models import Staff
from .security import hasher, merchant_actor, verify_password, password_version

logger = logging.getLogger("pruvs.business.password_reset")
router = APIRouter(prefix="/v1/merchant/password", tags=["Merchant password recovery"])
SUCCESS = {"message": "If an active account exists, a recovery link will be emailed."}
RESET_TTL = timedelta(minutes=20)


class RecoveryRequest(BaseModel):
    email: EmailStr


class RecoveryConfirm(BaseModel):
    token: str = Field(min_length=60, max_length=4096)
    new_password: str = Field(min_length=15, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=15, max_length=128)


def _enabled(db: Session) -> None:
    if os.getenv("PRUVS_BUSINESS_PASSWORD_RESET_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Merchant account recovery is not enabled")
    if not os.getenv("RESEND_API_KEY") or not os.getenv("RESEND_FROM_EMAIL"):
        raise HTTPException(503, "Merchant email recovery is not configured")
    if not inspect(db.get_bind()).has_table(MerchantSignupRate.__tablename__):
        raise HTTPException(503, "Merchant account recovery database schema is not ready")


def _reset_url(token: str) -> str:
    origin = os.getenv("PRUVS_BUSINESS_PUBLIC_ORIGIN", "").strip().rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(503, "Merchant recovery public origin is not configured")
    return origin + "/business/merchant-reset.html#token=" + token


def _token(staff: Staff, *, invite: bool = False) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"iss": "pruvs-business", "aud": "pruvs-business-password-reset",
         "sub": staff.id, "typ": "merchant_staff_invite" if invite else "merchant_password_reset",
         "pv": password_version(staff.password_hash),
         "iat": now, "exp": now + RESET_TTL, "jti": secrets.token_hex(16)},
        get_settings().business_jwt_secret, algorithm="HS256",
    )


def _send_reset(staff: Staff, *, invite: bool = False) -> None:
    url = _reset_url(_token(staff, invite=invite))
    body = {
        "from": os.environ["RESEND_FROM_EMAIL"],
        "to": [staff.email],
        "subject": "Invitation to Pruvs Business" if invite else "Reset your Pruvs Business password",
        "text": "Use this single-use Pruvs Business password setup link within 20 minutes: " + url
                + "\nIf you did not request this, ignore it.",
        "html": '<p>Reset your Pruvs Business password using the link below (expires in 20 minutes):</p>'
                '<p><a href="' + html.escape(url, quote=True) + '">Reset password</a></p>'
                '<p>If you did not request this, ignore it.</p>',
    }
    request = UrlRequest(
        "https://api.resend.com/emails", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
                 "Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "PruvsBusiness/PasswordRecovery"}, method="POST")
    try:
        with urlopen(request, timeout=12) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError("Unexpected mail provider response")
    except (HTTPError, URLError, RuntimeError, OSError):
        logger.warning("Merchant recovery email provider failure (no recipient details)")
        raise HTTPException(503, "Merchant recovery email temporarily unavailable") from None


@router.post("/forgot", status_code=202)
def forgot(payload: RecoveryRequest, request: Request, db: Session = Depends(get_db)):
    _enabled(db)
    email = str(payload.email).strip().lower()
    # Persistent, privacy-preserving IP + email rate limits. The generic
    # response is identical for existing/non-existing addresses.
    with db.begin():
        source = request.client.host if request.client else "unknown"
        enforce_limit(db, "password-recovery-ip:" + source, max_attempts=12)
        enforce_limit(db, "password-recovery-email:" + email, max_attempts=3)
        staff = db.scalar(select(Staff).where(Staff.email == email))
        if staff and staff.active:
            try:
                _send_reset(staff)
            except HTTPException:
                # Never disclose account existence from delivery outcome.
                logger.warning("A merchant password recovery request could not be delivered")
    return SUCCESS


@router.post("/confirm")
def confirm(payload: RecoveryConfirm, db: Session = Depends(get_db)):
    _enabled(db)
    try:
        data = jwt.decode(payload.token, get_settings().business_jwt_secret,
                          algorithms=["HS256"], issuer="pruvs-business",
                          audience="pruvs-business-password-reset",
                          options={"require": ["iss", "aud", "sub", "exp", "iat", "jti"]},
                          leeway=5)
    except jwt.PyJWTError:
        raise HTTPException(400, "Invalid or expired reset link") from None
    if data.get("typ") not in ("merchant_password_reset", "merchant_staff_invite"):
        raise HTTPException(400, "Invalid or expired reset link")
    with db.begin():
        staff = db.scalar(select(Staff).where(Staff.id == data["sub"]).with_for_update())
        if (not staff or (not staff.active and data.get('typ') != 'merchant_staff_invite')
            or (staff.active and data.get('typ') == 'merchant_staff_invite')
            or not secrets.compare_digest(str(data.get('pv', '')), password_version(staff.password_hash))):
            raise HTTPException(400, "Invalid or already-used reset link")
        if verify_password(payload.new_password, staff.password_hash):
            raise HTTPException(422, "Choose a different password")
        staff.password_hash = hasher.hash(payload.new_password)
        if data.get('typ') == 'merchant_staff_invite':
            staff.active = True
    return {"ok": True, "message": "Password updated. Sign in again."}


@router.post("/change")
def change(payload: PasswordChange, staff: Staff = Depends(merchant_actor),
           db: Session = Depends(get_db)):
    # merchant_actor already queried using this same session, so a transaction
    # is active; do not nest db.begin() here.
    locked = db.scalar(select(Staff).where(Staff.id == staff.id).with_for_update())
    if not locked or not locked.active or not verify_password(
        payload.current_password, locked.password_hash
    ):
        raise HTTPException(403, "Current password is incorrect")
    if verify_password(payload.new_password, locked.password_hash):
        raise HTTPException(422, "Choose a different password")
    locked.password_hash = hasher.hash(payload.new_password)
    db.commit()
    return {"ok": True, "message": "Password updated. Sign in again."}
