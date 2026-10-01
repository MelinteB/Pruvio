"""WebAuthn/passkey support for Pruvs.

Biometric data never reaches Pruvs. The operating system / authenticator checks
Face ID, fingerprint, Windows Hello, device PIN, or a security key locally and
returns a signed WebAuthn assertion which Pruvs verifies cryptographically.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.passkey_credential import PasskeyCredential
from app.models.user import User

try:
    from webauthn import (
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    WEBAUTHN_LIBRARY_AVAILABLE = True
except ImportError:  # keeps the rest of the app bootable if dependency installation is incomplete
    WEBAUTHN_LIBRARY_AVAILABLE = False


def _enabled(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def passkeys_enabled() -> bool:
    return _enabled("PASSKEY_ENABLED", "true") and WEBAUTHN_LIBRARY_AVAILABLE


def _origin() -> str:
    configured = os.getenv("PASSKEY_ORIGIN", "").strip().rstrip("/")
    if configured:
        return configured
    public = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    return public


def _rp_id() -> str:
    configured = os.getenv("PASSKEY_RP_ID", "").strip()
    if configured:
        return configured
    parsed = urlparse(_origin())
    return parsed.hostname or "127.0.0.1"


def _rp_name() -> str:
    return os.getenv("PASSKEY_RP_NAME", "Pruvs").strip() or "Pruvs"


def passkey_config_summary() -> dict:
    return {
        "enabled": passkeys_enabled(),
        "library_available": WEBAUTHN_LIBRARY_AVAILABLE,
        "rp_id": _rp_id(),
        "origin": _origin(),
    }


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    raw = value.encode("ascii")
    raw += b"=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw)


def _enum_value(value) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _stable_user_handle(user: User) -> bytes:
    secret = os.getenv("PASSKEY_USER_HANDLE_SECRET") or os.getenv("OTP_SECRET") or "pruvio-local-user-handle"
    return hashlib.sha256(f"{secret}:user:{user.id}".encode("utf-8")).digest()


def list_user_passkeys(db: Session, user_id: int) -> list[PasskeyCredential]:
    return (
        db.query(PasskeyCredential)
        .filter(PasskeyCredential.user_id == user_id)
        .order_by(PasskeyCredential.created_at.desc())
        .all()
    )


def begin_passkey_registration(db: Session, user: User) -> tuple[object, str]:
    if not passkeys_enabled():
        raise ValueError("Passkeys are not available on this server yet.")
    if user.status != "active":
        raise ValueError("Your account must be active before adding a passkey.")

    exclude = [
        PublicKeyCredentialDescriptor(id=_b64url_decode(row.credential_id))
        for row in list_user_passkeys(db, user.id)
    ]
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=_stable_user_handle(user),
        user_name=user.email or user.phone_number or f"user-{user.id}",
        user_display_name=user.name or user.email or user.phone_number or "Pruvs user",
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return options.challenge, options_to_json(options)


def complete_passkey_registration(
    db: Session,
    user: User,
    *,
    challenge: bytes,
    browser_credential: dict,
    device_name: str | None = None,
) -> PasskeyCredential:
    if not passkeys_enabled():
        raise ValueError("Passkeys are not available on this server yet.")

    verification = verify_registration_response(
        credential=browser_credential,
        expected_challenge=challenge,
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
        require_user_verification=True,
    )
    credential_id = _b64url_encode(verification.credential_id)
    existing = db.query(PasskeyCredential).filter(PasskeyCredential.credential_id == credential_id).first()
    if existing:
        raise ValueError("This passkey is already registered.")

    response = browser_credential.get("response") or {}
    transports = response.get("transports") or []
    row = PasskeyCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=_b64url_encode(verification.credential_public_key),
        sign_count=int(verification.sign_count or 0),
        transports=",".join(str(v) for v in transports) or None,
        device_type=_enum_value(getattr(verification, "credential_device_type", None)),
        backed_up=bool(getattr(verification, "credential_backed_up", False)),
        device_name=(device_name or "").strip()[:120] or "Passkey",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def begin_passkey_authentication() -> tuple[object, str]:
    if not passkeys_enabled():
        raise ValueError("Passkeys are not available on this server yet.")
    options = generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options.challenge, options_to_json(options)


def complete_passkey_authentication(
    db: Session,
    *,
    challenge: bytes,
    browser_credential: dict,
) -> User:
    if not passkeys_enabled():
        raise ValueError("Passkeys are not available on this server yet.")
    credential_id = str(browser_credential.get("id") or browser_credential.get("rawId") or "").strip()
    if not credential_id:
        raise ValueError("The browser did not return a passkey credential.")

    row = db.query(PasskeyCredential).filter(PasskeyCredential.credential_id == credential_id).first()
    if row is None:
        # Some clients may normalize the credential ID differently. Compare the raw bytes form as fallback.
        try:
            target = _b64url_decode(credential_id)
            rows = db.query(PasskeyCredential).all()
            row = next((item for item in rows if _b64url_decode(item.credential_id) == target), None)
        except Exception:
            row = None
    if row is None:
        raise ValueError("This passkey is not registered with Pruvs.")

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None or user.status != "active":
        raise ValueError("The account linked to this passkey is unavailable.")

    verification = verify_authentication_response(
        credential=browser_credential,
        expected_challenge=challenge,
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
        credential_public_key=_b64url_decode(row.public_key),
        credential_current_sign_count=int(row.sign_count or 0),
        require_user_verification=True,
    )
    row.sign_count = int(verification.new_sign_count or 0)
    row.last_used_at = datetime.utcnow()
    user.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def delete_passkey(db: Session, *, user_id: int, passkey_id: int) -> None:
    row = (
        db.query(PasskeyCredential)
        .filter(PasskeyCredential.id == passkey_id, PasskeyCredential.user_id == user_id)
        .first()
    )
    if row is None:
        raise ValueError("Passkey not found.")
    db.delete(row)
    db.commit()


def _browser_common_helpers() -> str:
    return r'''
const b64urlToBuffer = (value) => {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '='.repeat((4 - base64.length % 4) % 4);
  const raw = atob(padded);
  return Uint8Array.from(raw, c => c.charCodeAt(0)).buffer;
};
const bufferToB64url = (value) => {
  const bytes = new Uint8Array(value);
  let binary = '';
  bytes.forEach(b => binary += String.fromCharCode(b));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
};
if (!window.PublicKeyCredential || !navigator.credentials) {
  throw new Error('Passkeys are not supported by this browser or device.');
}
'''


def registration_browser_javascript(options_json: str) -> str:
    payload = json.dumps(options_json)
    return f'''return await (async () => {{
{_browser_common_helpers()}
const publicKey = JSON.parse({payload});
publicKey.challenge = b64urlToBuffer(publicKey.challenge);
publicKey.user.id = b64urlToBuffer(publicKey.user.id);
(publicKey.excludeCredentials || []).forEach(item => item.id = b64urlToBuffer(item.id));
const credential = await navigator.credentials.create({{publicKey}});
return {{
  id: credential.id,
  rawId: bufferToB64url(credential.rawId),
  type: credential.type,
  authenticatorAttachment: credential.authenticatorAttachment || null,
  clientExtensionResults: credential.getClientExtensionResults(),
  response: {{
    clientDataJSON: bufferToB64url(credential.response.clientDataJSON),
    attestationObject: bufferToB64url(credential.response.attestationObject),
    transports: credential.response.getTransports ? credential.response.getTransports() : []
  }}
}};
}})();'''


def authentication_browser_javascript(options_json: str) -> str:
    payload = json.dumps(options_json)
    return f'''return await (async () => {{
{_browser_common_helpers()}
const publicKey = JSON.parse({payload});
publicKey.challenge = b64urlToBuffer(publicKey.challenge);
(publicKey.allowCredentials || []).forEach(item => item.id = b64urlToBuffer(item.id));
const credential = await navigator.credentials.get({{publicKey}});
return {{
  id: credential.id,
  rawId: bufferToB64url(credential.rawId),
  type: credential.type,
  authenticatorAttachment: credential.authenticatorAttachment || null,
  clientExtensionResults: credential.getClientExtensionResults(),
  response: {{
    clientDataJSON: bufferToB64url(credential.response.clientDataJSON),
    authenticatorData: bufferToB64url(credential.response.authenticatorData),
    signature: bufferToB64url(credential.response.signature),
    userHandle: credential.response.userHandle ? bufferToB64url(credential.response.userHandle) : null
  }}
}};
}})();'''
