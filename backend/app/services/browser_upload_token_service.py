import base64
import hashlib
import hmac
import json
import os
import time


_TOKEN_PURPOSE = "receipt_browser_upload"
_DEFAULT_TTL_SECONDS = 20 * 60


def _secret() -> bytes:
    """
    Reuse the NiceGUI storage secret so v6.8 does not require another Render secret.

    PRUVS_UPLOAD_TOKEN_SECRET may be set separately later if desired. The local
    development fallback intentionally mirrors app.main's storage-secret fallback.
    """
    value = (
        os.getenv("PRUVS_UPLOAD_TOKEN_SECRET")
        or os.getenv("PRUVIO_STORAGE_SECRET")
        or "pruvio-local-dev-secret-change-me"
    )
    return value.encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def create_browser_upload_token(
    user_id: int,
    *,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> str:
    if int(user_id) <= 0:
        raise ValueError("Invalid user id for browser upload token.")

    now = int(time.time())
    payload = {
        "uid": int(user_id),
        "iat": now,
        "exp": now + max(60, int(ttl_seconds)),
        "purpose": _TOKEN_PURPOSE,
    }
    payload_bytes = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload_part = _b64url_encode(payload_bytes)
    signature = hmac.new(
        _secret(),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_b64url_encode(signature)}"


def verify_browser_upload_token(token: str) -> int:
    if not token or "." not in token:
        raise ValueError("Missing or invalid receipt upload token.")

    try:
        payload_part, signature_part = token.split(".", 1)
        supplied_signature = _b64url_decode(signature_part)
    except Exception as error:
        raise ValueError("Invalid receipt upload token.") from error

    expected_signature = hmac.new(
        _secret(),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ValueError("Invalid receipt upload token signature.")

    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
        user_id = int(payload["uid"])
        expires_at = int(payload["exp"])
    except Exception as error:
        raise ValueError("Invalid receipt upload token payload.") from error

    if payload.get("purpose") != _TOKEN_PURPOSE:
        raise ValueError("Invalid receipt upload token purpose.")
    if user_id <= 0:
        raise ValueError("Invalid receipt upload token user.")
    if expires_at < int(time.time()):
        raise ValueError("Receipt upload token expired. Reload the upload page and try again.")

    return user_id
