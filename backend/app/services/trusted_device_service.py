import hashlib
import os
import secrets
from datetime import datetime, timedelta

from app.models.trusted_device import TrustedDevice
from app.models.user import User
from app.models.verification_code import VerificationCode

DEVICE_COOKIE = "pruvio_trusted_device"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def trusted_device_days() -> int:
    return max(1, min(365, int(os.getenv("TRUSTED_DEVICE_DAYS", "30"))))


def is_trusted_device(db, user, token: str | None) -> bool:
    if not user or user.status != "active" or not user.is_email_verified or not token or len(token) > 128:
        return False
    return db.query(TrustedDevice.id).filter(
        TrustedDevice.user_id == user.id,
        TrustedDevice.token_hash == _hash(token),
        TrustedDevice.revoked_at.is_(None),
        TrustedDevice.expires_at > datetime.utcnow(),
    ).first() is not None



def trusted_device_user_id(db, token: str | None) -> int | None:
    """Return the active account bound to the browser's current trusted-device token."""
    if not token or len(token) > 128:
        return None
    now = datetime.utcnow()
    row = (
        db.query(TrustedDevice.user_id)
        .join(User, User.id == TrustedDevice.user_id)
        .filter(
            TrustedDevice.token_hash == _hash(token),
            TrustedDevice.revoked_at.is_(None),
            TrustedDevice.expires_at > now,
            User.status == "active",
            User.is_email_verified.is_(True),
        )
        .first()
    )
    return int(row[0]) if row else None

def create_device_claim(db, user) -> str:
    """Create a two-minute, single-use grant after successful OTP verification."""
    if user.status != "active" or not user.is_email_verified:
        raise ValueError("This account is not active.")
    now = datetime.utcnow()
    claim = secrets.token_urlsafe(32)
    db.add(TrustedDevice(
        user_id=user.id, claim_hash=_hash(claim),
        claim_expires_at=now + timedelta(minutes=2),
        expires_at=now + timedelta(days=trusted_device_days()),
    ))
    db.commit()
    return claim


def consume_device_claim(db, claim: str) -> str:
    if not claim or len(claim) > 128:
        raise ValueError("Device verification expired. Sign in again.")
    token = secrets.token_urlsafe(48)
    now = datetime.utcnow()
    count = db.query(TrustedDevice).filter(
        TrustedDevice.claim_hash == _hash(claim),
        TrustedDevice.user_id.in_(db.query(User.id).filter(User.status == "active", User.is_email_verified.is_(True))),
        TrustedDevice.claim_expires_at > now,
        TrustedDevice.revoked_at.is_(None),
        TrustedDevice.token_hash.is_(None),
    ).update({"claim_hash": None, "claim_expires_at": None, "token_hash": _hash(token)}, synchronize_session=False)
    db.commit()
    if count != 1:
        raise ValueError("Device verification expired. Sign in again.")
    return token


def revoke_trusted_devices(db, user_id: int) -> None:
    db.query(VerificationCode).filter(
        VerificationCode.user_id == user_id, VerificationCode.purpose == "login",
        VerificationCode.status == "pending",
    ).update({"status": "expired", "code_ciphertext": None}, synchronize_session=False)
    db.query(TrustedDevice).filter(
        TrustedDevice.user_id == user_id, TrustedDevice.revoked_at.is_(None),
    ).update({"revoked_at": datetime.utcnow()}, synchronize_session=False)

