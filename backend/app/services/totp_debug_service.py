"""Developer-only RFC 6238 TOTP helper.

This deliberately uses only the Python standard library so Pruvio does not need
an additional TOTP dependency. The secret is supplied by Render/local env and is
never stored in the user table.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import struct
import time
from urllib.parse import quote

import qrcode

from app.models.user import User


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def totp_debug_enabled() -> bool:
    return _enabled("DEV_TOTP_ENABLED", "false")


def _allowed_emails() -> set[str]:
    raw = os.getenv("DEV_TOTP_ALLOWED_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def totp_allowed_for_user(user: User | None) -> bool:
    if not user or not totp_debug_enabled() or user.status != "active":
        return False
    email = (user.email or "").strip().lower()
    return bool(email and user.is_email_verified and email in _allowed_emails())


def _normalize_base32(value: str) -> str:
    return "".join(ch for ch in value.strip().upper().replace(" ", "") if ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def get_totp_secret(user: User | None = None) -> str:
    explicit = _normalize_base32(os.getenv("DEV_TOTP_SECRET", ""))
    if explicit:
        master = _secret_bytes(explicit)
    else:
        # Stable fallback for local development. In Render, configure DEV_TOTP_SECRET
        # explicitly so rotating OTP_SECRET cannot invalidate the Authenticator entry.
        master = os.getenv("OTP_SECRET", "pruvio-local-dev-otp-secret").encode("utf-8")

    if user is not None:
        account = (user.email or user.phone_number or f"user-{user.id}").strip().lower().encode("utf-8")
        digest = hmac.new(master, b"pruvio-developer-totp-user-v1:" + account, hashlib.sha256).digest()
    else:
        digest = hmac.new(master, b"pruvio-developer-totp-v1", hashlib.sha256).digest()
    return base64.b32encode(digest[:20]).decode("ascii").rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    clean = _normalize_base32(secret)
    padding = "=" * ((8 - len(clean) % 8) % 8)
    return base64.b32decode(clean + padding, casefold=True)


def generate_totp(secret: str | None = None, *, at_time: int | None = None, digits: int = 6, period: int = 30) -> str:
    key = _secret_bytes(secret or get_totp_secret())
    counter = int((at_time if at_time is not None else time.time()) // period)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def verify_totp(
    code: str,
    *,
    secret: str | None = None,
    user: User | None = None,
    valid_window: int = 1,
    period: int = 30,
) -> bool:
    candidate = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(candidate) != 6:
        return False
    now = int(time.time())
    for step in range(-valid_window, valid_window + 1):
        expected = generate_totp(secret or get_totp_secret(user), at_time=now + step * period, period=period)
        if hmac.compare_digest(candidate, expected):
            return True
    return False


def provisioning_uri(user: User) -> str:
    account = (user.email or user.phone_number or f"user-{user.id}").strip()
    issuer = os.getenv("DEV_TOTP_ISSUER", "Pruvio Developer").strip() or "Pruvio Developer"
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={quote(get_totp_secret(user))}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def provisioning_qr_data_uri(user: User) -> str:
    image = qrcode.make(provisioning_uri(user))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{payload}"
