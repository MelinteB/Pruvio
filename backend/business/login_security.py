"""Database-backed merchant login throttling using the existing rate table.

Count attempts before password verification; commit even if credentials are invalid.
No raw email or connection address is stored. No new user or schema is created.
"""
import hashlib
import hmac
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import case, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .merchant_enrollment import MerchantSignupRate
from .models import Merchant, Staff
from .security import encode_merchant_token, hasher, verify_password

WINDOW_MINUTES = 15
IP_LIMIT = 30
ACCOUNT_LIMIT = 8
# Unknown accounts still perform Argon2 verification to reduce timing leakage.
_DUMMY_HASH = hasher.hash("pruvs-dummy-password-not-an-account")


def _bucket(key, value):
    secret = get_settings().business_jwt_secret.encode()
    return hmac.new(secret, ("merchant-login-v1:" + key + ":" + value).encode(),
                    hashlib.sha256).hexdigest()


def consume_attempts(db, email, ip, *, now=None):
    now = now or datetime.utcnow()
    table = MerchantSignupRate.__table__
    dialect = db.get_bind().dialect.name
    if dialect not in ("postgresql", "sqlite"):
        raise HTTPException(503, "Authentication temporarily unavailable")
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    expired = table.c.window_started_at <= now - timedelta(minutes=WINDOW_MINUTES)
    buckets = [(_bucket("ip", ip), IP_LIMIT), (_bucket("account", email), ACCOUNT_LIMIT)]
    try:
        # Consistent lock order across simultaneous login requests.
        for bucket, maximum in sorted(buckets):
            stmt = insert(table).values(bucket_hash=bucket, window_started_at=now, attempts=1)
            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c.bucket_hash],
                set_={"attempts": case((expired, 1), else_=table.c.attempts + 1),
                      "window_started_at": case((expired, now), else_=table.c.window_started_at)},
                where=or_(expired, table.c.attempts < maximum)).returning(table.c.attempts)
            if db.execute(stmt).scalar_one_or_none() is None:
                db.rollback()
                raise HTTPException(429, "Too many sign-in attempts. Try again later.",
                                    headers={"Retry-After": str(WINDOW_MINUTES * 60)})
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Authentication temporarily unavailable") from None


def authenticate_merchant(payload, request, db):
    email = payload.email.strip().lower()
    source = request.client.host if request.client else "unknown"
    consume_attempts(db, email, source)
    staff = db.scalar(select(Staff).where(Staff.email == email))
    valid = verify_password(payload.password, staff.password_hash if staff else _DUMMY_HASH)
    merchant = db.get(Merchant, staff.merchant_id) if staff else None
    if not valid or not staff or not staff.active or not merchant or merchant.status != "active":
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": encode_merchant_token(staff), "token_type": "bearer", "expires_in": 7200}
