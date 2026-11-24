"""Staging-only Core social identity foundation.

Supported authorization methods:
- Google / Yahoo / Apple: verified OIDC identity; sign-up uses verified email.
- Facebook: OAuth subject. Link to an already authenticated Pruvs account.
- TikTok: Login Kit open_id. Link to an already authenticated Pruvs account.
- Instagram: API with Instagram Login for professional accounts only; link-only.

No provider tokens are stored. No existing Pruvs account is linked by matching
email. State and signup tickets are HMAC signed and bound to an HttpOnly cookie.
Disable globally until provider compliance, staging verification and legal review.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from urllib.parse import quote, urlencode, urlparse

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.legal_content import TERMS_VERSION, PRIVACY_VERSION
from app.models.social_identity import SocialAccount
from app.models.user import User
from app.react_app.auth import (
    COOKIE, current, digest, issue, limit, secure,
)
from app.services.onboarding_otp_service import verify_registration_email
from app.services.phone_numbers import normalize_signup_phone
from app.services.username_service import derive_available_username, check_username_available
from app.usernames import username_key

router = APIRouter(prefix="/api/v1/auth/social", tags=["Social sign-in"])
STATE_COOKIE = "pruvs_social_flow"
APPLE_BRIDGE_COOKIE = "pruvs_apple_oauth_bridge"
SIGNUP_COOKIE = "pruvs_social_pending"
COOKIE_PATH = "/api/v1/auth/social"
PROVIDERS = ("google", "yahoo", "facebook", "instagram", "tiktok", "apple")
LINK_ONLY = frozenset(("facebook", "instagram", "tiktok"))
AUTHORIZE = {
    "google": "https://accounts.google.com/o/oauth2/v2/auth",
    "apple": "https://appleid.apple.com/auth/authorize",
    "yahoo": "https://api.login.yahoo.com/oauth2/request_auth",
    "facebook": "https://www.facebook.com/v24.0/dialog/oauth",
    "instagram": "https://www.instagram.com/oauth/authorize",
    "tiktok": "https://www.tiktok.com/v2/auth/authorize/",
}
TOKEN = {
    "google": "https://oauth2.googleapis.com/token",
    "apple": "https://appleid.apple.com/auth/token",
    "yahoo": "https://api.login.yahoo.com/oauth2/get_token",
    "facebook": "https://graph.facebook.com/v24.0/oauth/access_token",
    "instagram": "https://api.instagram.com/oauth/access_token",
    "tiktok": "https://open.tiktokapis.com/v2/oauth/token/",
}
SCOPES = {
    "google": "openid email profile",
    "apple": "name email",
    "yahoo": "openid email profile",
    "facebook": "public_profile,email",
    "instagram": "instagram_business_basic",
    "tiktok": "user.info.basic",
}
JWKS = {
    "google": "https://www.googleapis.com/oauth2/v3/certs",
    "apple": "https://appleid.apple.com/auth/keys",
    "yahoo": "https://api.login.yahoo.com/openid/v1/certs",
}
ISSUER = {
    "google": ("https://accounts.google.com", "accounts.google.com"),
    "apple": ("https://appleid.apple.com",),
    "yahoo": ("https://api.login.yahoo.com",),
}


class CompleteEmailSignup(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    code: str = Field(min_length=6, max_length=6)
    challenge_id: str = Field(min_length=1, max_length=128)


class CompleteSignup(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    username: str | None = Field(default=None, max_length=80)
    phone_number: str = Field(min_length=6, max_length=50)
    phone_country: str = Field(default='RO',min_length=2,max_length=2)
    accepted_terms: bool
    accepted_privacy: bool
    marketing_opt_in: bool = False
    notifications_opt_in: bool = False


def _state_secret():
    # Preserve the staging-only shared secret for other experimental providers.
    key = os.getenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", "")
    if len(key) >= 32:
        return key.encode("utf-8")
    # Google works with the same three short names as production. Derive a
    # domain-separated signing key; no fourth Google env variable is required.
    secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if secret:
        return hmac.new(secret.encode("utf-8"),
                        b"pruvs/google/oauth-state/v1", hashlib.sha256).digest()
    raise HTTPException(503, "Social authentication is not configured")


def _globally_enabled():
    return os.getenv("PRUVS_SOCIAL_LOGIN_ENABLED", "false").lower() == "true"


def _client(provider):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Provider not supported")
    # Match the production Google group exactly; other staging providers
    # retain their original opt-in settings and remain disabled in the UI.
    prefix = "GOOGLE" if provider == "google" else "PRUVS_SOCIAL_" + provider.upper()
    return (os.getenv(prefix + "_CLIENT_ID", "").strip(),
            os.getenv(prefix + "_CLIENT_SECRET", "").strip(),
            os.getenv(prefix + "_ENABLED", "false").strip().lower() == "true")


def _configured(provider):
    client_id, secret, enabled = _client(provider)
    if provider == "google":
        # No legacy PRUVS_SOCIAL_* switch or separate state secret needed.
        return bool(enabled and client_id and secret)
    common = (_globally_enabled() and enabled and client_id and
              len(os.getenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", "")) >= 32)
    if provider == "apple":
        return bool(common and os.getenv("PRUVS_SOCIAL_APPLE_TEAM_ID") and
                    os.getenv("PRUVS_SOCIAL_APPLE_KEY_ID") and
                    os.getenv("PRUVS_SOCIAL_APPLE_PRIVATE_KEY_BASE64"))
    return bool(common and secret)


def _social_enabled():
    # Google has its own three-variable configuration; the legacy global switch
    # remains relevant only to the other experimental providers.
    return _globally_enabled() or _configured("google")


def _ensure_provider(provider):
    if not _configured(provider):
        raise HTTPException(503, "This social sign-in provider is unavailable")

def _schema_ready(db):
    if not inspect(db.get_bind()).has_table(SocialAccount.__tablename__):
        raise HTTPException(503, "Social identity database migration is not applied")


def _origin():
    raw = os.getenv("PUBLIC_BASE_URL", "https://pruvs.io").strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(503, "Social sign-in requires an exact HTTPS public origin")
    return raw


def _redirect_uri(provider):
    return _origin() + "/api/v1/auth/social/" + provider + "/callback"


def _internal_next(value):
    return value if value and value.startswith("/") and not value.startswith("//") and "\\" not in value and not any(ord(ch)<32 for ch in value) else "/"


def _b64(raw: bytes):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _seal(body: dict):
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    mac = _b64(hmac.new(_state_secret(), raw.encode(), hashlib.sha256).digest())
    return raw + "." + mac


def _unseal(raw: str, *, max_age: int):
    try:
        part, signature = raw.split(".", 1)
        correct = _b64(hmac.new(_state_secret(), part.encode(), hashlib.sha256).digest())
        if not secrets.compare_digest(correct, signature):
            raise ValueError("invalid signature")
        data = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        age = int(time.time()) - int(data["iat"])
        if age < -30 or age > max_age:
            raise ValueError("expired")
        return data
    except (ValueError, KeyError, TypeError, OverflowError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(400, "Social authentication session expired. Start again.") from None


def _clear(response, cookie):
    response.delete_cookie(cookie, path=COOKIE_PATH, secure=secure(), samesite="lax", httponly=True)


def _cookie(response, name, value, seconds, *, apple_post=False):
    # Apple's cross-site form POST needs SameSite=None for the transient state
    # cookie only; the primary login session remains SameSite=Lax.
    response.set_cookie(name, value, max_age=seconds, httponly=True,
                        secure=True if apple_post else secure(),
                        samesite="none" if apple_post else "lax", path=COOKIE_PATH)


def _apple_client_secret(client_id: str) -> str:
    encoded = os.getenv("PRUVS_SOCIAL_APPLE_PRIVATE_KEY_BASE64", "")
    team_id = os.getenv("PRUVS_SOCIAL_APPLE_TEAM_ID", "")
    key_id = os.getenv("PRUVS_SOCIAL_APPLE_KEY_ID", "")
    if not encoded or not team_id or not key_id:
        raise HTTPException(503, "Apple sign-in is not configured")
    try:
        private_key = base64.b64decode(encoded, validate=True).decode("utf-8")
        now = int(time.time())
        return jwt.encode({"iss":team_id, "iat":now, "exp":now+86400*7,
                           "aud":"https://appleid.apple.com", "sub":client_id},
                          private_key, algorithm="ES256", headers={"kid":key_id})
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error, jwt.PyJWTError):
        raise HTTPException(503, "Apple private-key configuration is invalid") from None


def _fetch(url, *, method="GET", params=None, data=None, headers=None, auth=None):
    try:
        with httpx.Client(timeout=8, follow_redirects=False) as client:
            r = client.request(method, url, params=params, data=data, headers=headers, auth=auth)
        if r.status_code < 200 or r.status_code >= 300 or len(r.content) > 65536:
            raise ValueError("Provider refused request")
        result = r.json()
        if not isinstance(result, dict):
            raise ValueError("Invalid provider response")
        return result
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Social provider verification is temporarily unavailable") from None


def _oidc_identity(provider, tokens, client_id, nonce):
    raw = tokens.get("id_token")
    if not isinstance(raw, str) or len(raw) > 12000:
        raise HTTPException(502, "Identity provider did not return an ID token")
    try:
        jwks = jwt.PyJWKClient(JWKS[provider])
        signing_key = jwks.get_signing_key_from_jwt(raw)
        claims = jwt.decode(raw, signing_key.key, algorithms=["RS256"],
                            issuer=list(ISSUER[provider]), audience=client_id,
                            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
                            leeway=30)
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise ValueError("OIDC nonce mismatch")
    except (jwt.PyJWTError, ValueError, TypeError, jwt.PyJWKClientError, OSError):
        raise HTTPException(502, "Identity provider token verification failed") from None
    subject = str(claims.get("sub", ""))
    if not subject or len(subject) > 255:
        raise HTTPException(502, "Identity provider subject is invalid")
    return {"subject": subject, "name": str(claims.get("name") or "")[:255],
            "email": str(claims.get("email") or "").lower()[:255],
            "verified": claims.get("email_verified") is True or claims.get("email_verified") == "true"}


def _oauth_identity(provider, code, client_id, secret, redirect_uri, flow):
    data = {"code": code, "redirect_uri": redirect_uri, "grant_type": "authorization_code"}
    if provider in ("google", "yahoo", "apple"):
        data.update(client_id=client_id,
                    client_secret=_apple_client_secret(client_id) if provider == "apple" else secret)
        if provider == "google":
            data["code_verifier"] = flow["verifier"]
        tokens = _fetch(TOKEN[provider], method="POST", data=data)
        return _oidc_identity(provider, tokens, client_id, flow["nonce"])
    if provider == "facebook":
        tokens = _fetch(TOKEN[provider], params={
            "code": code, "client_id": client_id, "client_secret": secret,
            "redirect_uri": redirect_uri})
        access = str(tokens.get("access_token") or "")
        if not access:
            raise HTTPException(502, "Facebook authorization unsuccessful")
        proof = hmac.new(secret.encode(), access.encode(), hashlib.sha256).hexdigest()
        profile = _fetch("https://graph.facebook.com/v24.0/me",
            params={"fields": "id,name,email", "appsecret_proof": proof},
            headers={"Authorization": "Bearer " + access})
        return {"subject": str(profile.get("id") or ""), "name": str(profile.get("name") or "")[:255],
                "email": "", "verified": False}
    if provider == "instagram":
        tokens = _fetch(TOKEN[provider], method="POST", data={
            **data, "client_id": client_id, "client_secret": secret})
        # Provider responses may be flat or wrapped in a single data entry.
        # Refuse ambiguous data rather than associating the wrong identity.
        if "data" in tokens:
            entries = tokens.get("data")
            if not isinstance(entries, list) or len(entries) != 1 or tokens.get("user_id") or tokens.get("access_token"):
                raise HTTPException(502, "Unexpected Instagram identity response")
            tokens = entries[0]
            if not isinstance(tokens, dict):
                raise HTTPException(502, "Unexpected Instagram identity response")
        return {"subject": str(tokens.get("user_id") or ""), "name": "Instagram professional account",
                "email": "", "verified": False}
    if provider == "tiktok":
        tokens = _fetch(TOKEN[provider], method="POST", data={
            **data, "client_key": client_id, "client_secret": secret})
        return {"subject": str(tokens.get("open_id") or ""), "name": "TikTok account",
                "email": "", "verified": False}
    raise HTTPException(404, "Provider unavailable")


@router.get("/providers")
def providers(db=Depends(get_db)):
    schema_ready = inspect(db.get_bind()).has_table(SocialAccount.__tablename__) if _social_enabled() else False
    return {"providers": [{"id": p, "enabled": p == 'google' and _configured(p) and schema_ready,
             "signup": True,
             "note": ("Business or Creator Instagram accounts only; Pruvs email OTP required"
                      if p == "instagram" else
                      "Pruvs email OTP required for new accounts" if p in LINK_ONLY else "")}
            for p in PROVIDERS]}


@router.get("/{provider}/start")
def start(provider: str, request: Request,
          mode: str = Query("login", pattern="^(login|link)$"),
          next: str = "/", db=Depends(get_db)):
    _ensure_provider(provider)
    _schema_ready(db)
    limit(db, request, "social-start", 25)
    link_uid = None
    login_bind = ""
    if mode == "link":
        user, _session = current(request, db)
        link_uid = user.id
        login_bind = digest(request.cookies.get(COOKIE, ""))
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    body = {"iat": int(time.time()), "state": state, "nonce": nonce,
            "verifier": verifier, "provider": provider, "mode": mode,
            "uid": link_uid, "session_hash": login_bind, "next": _internal_next(next)}
    client_id, _secret, _ = _client(provider)
    params = {"client_id": client_id, "redirect_uri": _redirect_uri(provider),
              "response_type": "code", "state": state, "scope": SCOPES[provider]}
    if provider in ("google", "yahoo", "apple"):
        params["nonce"] = nonce
    if provider == "google":
        params["code_challenge"] = _b64(hashlib.sha256(verifier.encode()).digest())
        params["code_challenge_method"] = "S256"
        params["prompt"] = "select_account"
    if provider == "apple":
        params["response_type"] = "code id_token"
        params["response_mode"] = "form_post"
    if provider == "tiktok":
        params["client_key"] = params.pop("client_id")
    if provider == "instagram":
        params["enable_fb_login"] = "0"
    response = RedirectResponse(AUTHORIZE[provider] + "?" + urlencode(params),
                                status_code=302)
    _cookie(response, STATE_COOKIE, _seal(body), 600, apple_post=(provider=="apple"))
    return response


@router.post("/{provider}/callback")
async def apple_callback(provider: str, request: Request, db=Depends(get_db)):
    if provider != "apple":
        raise HTTPException(405, "Only Apple uses an OAuth form POST callback")
    if int(request.headers.get("content-length") or 0) > 8192:
        raise HTTPException(413, "Apple callback is too large")
    form = await request.form()
    return callback(provider, request, code=str(form.get("code") or ""),
                    state=str(form.get("state") or ""),
                    error=str(form.get("error") or ""), db=db)


@router.get("/apple/finish")
def apple_finish(request: Request, db=Depends(get_db)):
    _ensure_provider("apple")
    _schema_ready(db)
    ticket = _unseal(request.cookies.get(APPLE_BRIDGE_COOKIE, ""), max_age=90)
    if ticket.get("provider") != "apple":
        raise HTTPException(400, "Apple sign-in session invalid")
    response = _finish_verified_identity("apple", ticket["identity"], ticket["flow"], request, db)
    _clear(response, APPLE_BRIDGE_COOKIE)
    return response


@router.get("/{provider}/callback")
def callback(provider: str, request: Request, code: str = "", state: str = "",
             error: str = "", db=Depends(get_db)):
    if provider == "apple" and request.method != "POST":
        raise HTTPException(405, "Sign in with Apple requires a POST callback")
    _ensure_provider(provider)
    _schema_ready(db)
    flow = _unseal(request.cookies.get(STATE_COOKIE, ""), max_age=600)
    if flow.get("provider") != provider or not secrets.compare_digest(
        str(flow.get("state", "")), state
    ):
        raise HTTPException(400, "Social login state mismatch")
    if error or not code or len(code) > 2048:
        response = RedirectResponse("/login?social_error=cancelled", status_code=303)
        _clear(response, STATE_COOKIE)
        return response
    client_id, client_secret, _ = _client(provider)
    identity = _oauth_identity(provider, code, client_id, client_secret,
                               _redirect_uri(provider), flow)
    if not identity["subject"] or len(identity["subject"]) > 255:
        raise HTTPException(502, "Provider identity unavailable")
    if provider == "apple":
        # Finish from a same-origin GET: the Pruvs session cookie (Lax) isn't
        # sent on Apple's cross-site POST callback.
        response = RedirectResponse("/api/v1/auth/social/apple/finish", status_code=303)
        _cookie(response, APPLE_BRIDGE_COOKIE,
                _seal({"iat":int(time.time()),"provider":"apple",
                       "flow":flow,"identity":identity}),90)
        _clear(response, STATE_COOKIE)
        return response
    return _finish_verified_identity(provider, identity, flow, request, db)


def _finish_verified_identity(provider, identity, flow, request, db):
    existing = db.query(SocialAccount).filter_by(provider=provider,subject=identity["subject"]).first()
    if flow.get("mode") == "link":
        user, _session = current(request, db)
        if user.id != flow.get("uid") or not secrets.compare_digest(
            digest(request.cookies.get(COOKIE, "")), str(flow.get("session_hash", ""))
        ):
            raise HTTPException(403, "Social account linking session changed")
        if existing and existing.user_id != user.id:
            raise HTTPException(409, "This social identity belongs to another Pruvs account")
        other = db.query(SocialAccount).filter_by(user_id=user.id, provider=provider).first()
        if other and (not existing or other.id != existing.id):
            raise HTTPException(409, "Disconnect the previous identity before linking another")
        if not existing:
            db.add(SocialAccount(user_id=user.id,provider=provider,
                                 subject=identity["subject"],display_name=identity["name"]))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, "This provider identity is already linked") from None
        response = RedirectResponse("/account#account-social", status_code=303)
        _clear(response,STATE_COOKIE)
        return response
    if existing:
        user = db.get(User,existing.user_id)
        if not user or user.status != "active":
            raise HTTPException(403, "Account unavailable")
        existing.last_used_at = datetime.utcnow()
        response = RedirectResponse(_internal_next(flow.get("next")),status_code=303)
        issue(db,user,request,response)
        _clear(response,STATE_COOKIE)
        return response
    pending = {"iat":int(time.time()), "provider":provider,
               "subject":identity["subject"],"name":identity["name"],
               "email":identity["email"] if identity["verified"] else "",
               "verified":bool(identity["verified"]),"next":_internal_next(flow.get("next"))}
    response = RedirectResponse("/register?social=pending&next=" + quote(_internal_next(flow.get("next")),safe=""),status_code=303)
    _cookie(response,SIGNUP_COOKIE,_seal(pending),900)
    _clear(response,STATE_COOKIE)
    return response


@router.get("/pending")
def pending(request: Request, db=Depends(get_db)):
    if not _social_enabled():
        raise HTTPException(503, "Social registration is disabled")
    ticket = _unseal(request.cookies.get(SIGNUP_COOKIE, ""),max_age=900)
    if ticket.get("provider") not in PROVIDERS:
        raise HTTPException(400, "Social registration session invalid")
    _ensure_provider(ticket["provider"])
    can_complete = bool(ticket.get("verified") and ticket.get("email"))
    return {"provider":ticket["provider"],"name":ticket.get("name") or "",
            "email":ticket.get("email") if can_complete else "",
            "can_complete":can_complete,
            "requires_email_otp":not can_complete,
            "note": "Verify your email to finish social registration. Existing Pruvs users should sign in and link their provider in Account." if not can_complete else ""}


@router.post("/complete")
def complete(data: CompleteSignup, request: Request, response: Response,
             db=Depends(get_db)):
    if not _social_enabled():
        raise HTTPException(503, "Social registration is disabled")
    _schema_ready(db)
    limit(db,request,"social-registration",10)
    if request.cookies.get(COOKIE):
        raise HTTPException(409, "Sign out first or connect this provider in Account")
    ticket = _unseal(request.cookies.get(SIGNUP_COOKIE, ""),max_age=900)
    if not ticket.get("verified") or not ticket.get("email") or ticket.get("provider") not in ("google","yahoo","apple"):
        raise HTTPException(409, "Use verified email registration, then link your social account in Account")
    _ensure_provider(ticket["provider"])
    if not data.accepted_terms or not data.accepted_privacy:
        raise HTTPException(422, "Accept the Terms and Privacy Notice")
    email = str(ticket["email"]).strip().lower()
    if db.query(User.id).filter(func.lower(User.email)==email).first():
        raise HTTPException(409, "This email already belongs to Pruvs. Sign in and connect the provider in Account")
    if db.query(SocialAccount.id).filter_by(
        provider=ticket["provider"],subject=ticket["subject"]).first():
        raise HTTPException(409, "This provider identity is already connected")
    phone = normalize_signup_phone(data.phone_number,data.phone_country)
    if db.query(User.id).filter_by(phone_number=phone).first():
        raise HTTPException(409, "Phone number already registered")
    name = " ".join(data.name.split()).strip()
    chosen = (check_username_available(db,data.username) if data.username
              else derive_available_username(db,name))
    now = datetime.utcnow()
    user = User(phone_number=phone,name=name,email=email,status="active",
                username=chosen,username_key=username_key(chosen),
                password_hash=None,is_email_verified=True,is_phone_verified=False,
                accepted_terms=True,accepted_terms_at=now,terms_version=TERMS_VERSION,
                accepted_privacy=True,accepted_privacy_at=now,privacy_version=PRIVACY_VERSION,
                marketing_opt_in=data.marketing_opt_in,
                notifications_opt_in=data.notifications_opt_in,
                updated_at=now,last_seen_at=now)
    try:
        db.add(user);db.flush()
        db.add(SocialAccount(user_id=user.id,provider=ticket["provider"],
                             subject=ticket["subject"],display_name=ticket.get("name","")[:255]))
        db.flush()
        result = issue(db,user,request,response)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another account uses this identity, email or phone number") from None
    _clear(response,SIGNUP_COOKIE)
    return result


@router.post("/complete-email")
def complete_email(data: CompleteEmailSignup, request: Request, response: Response,
                   db=Depends(get_db)):
    """Complete OAuth-assisted signup for a provider lacking verified email.

    The existing Pruvs registration endpoint first collects Terms/Privacy consent,
    a unique email, phone and password and issues an email OTP. Only the Pruvs
    registration OTP (not provider supplied email) can activate the new user.
    """
    if not _social_enabled():
        raise HTTPException(503, "Social registration is disabled")
    _schema_ready(db)
    limit(db, request, "social-registration-otp", 15)
    if request.cookies.get(COOKIE):
        raise HTTPException(409, "Sign out before completing social registration")
    ticket = _unseal(request.cookies.get(SIGNUP_COOKIE, ""), max_age=900)
    provider = str(ticket.get("provider") or "")
    if provider not in PROVIDERS or not _configured(provider) or (ticket.get('verified') and ticket.get('email')):
        raise HTTPException(409, "This provider requires a different registration flow")
    subject = str(ticket.get("subject") or "")
    if not subject or len(subject) > 255:
        raise HTTPException(400, "Social provider identity is invalid")
    if db.query(SocialAccount.id).filter_by(provider=provider, subject=subject).first():
        raise HTTPException(409, "This provider identity is already connected")
    # This method only activates a pending registration with a valid OTP
    # matching the email on its Pruvs User record.
    user = verify_registration_email(db, data.email, data.code, challenge_id=data.challenge_id)
    if user.status != "active" or not user.is_email_verified:
        raise HTTPException(403, "Email verification is incomplete")
    # Only a freshly created account may inherit an unlinked external identity.
    # Prevent stale browser tickets being used to link unrelated existing users.
    if not user.created_at or (datetime.utcnow() - user.created_at).total_seconds() > 3600:
        raise HTTPException(409, "Please connect this account in Account after signing in")
    if db.query(SocialAccount.id).filter_by(provider=provider,subject=subject).first():
        raise HTTPException(409, "Social identity has already been linked")
    db.add(SocialAccount(user_id=user.id,provider=provider,
                         subject=subject,display_name=str(ticket.get("name") or "")[:255]))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Social identity is already associated with another account") from None
    result = issue(db,user,request,response)
    _clear(response, SIGNUP_COOKIE)
    return result


@router.get("/accounts")
def accounts(identity=Depends(current),db=Depends(get_db)):
    if not _social_enabled():
        return {"accounts": [], "disabled": True}
    _schema_ready(db)
    rows = db.query(SocialAccount).filter_by(user_id=identity[0].id).order_by(SocialAccount.provider).all()
    return {"accounts": [{"provider":r.provider,"name":r.display_name,
                          "connected_at":r.connected_at.isoformat()} for r in rows]}


@router.delete("/accounts/{provider}")
def unlink(provider: str, identity=Depends(current),db=Depends(get_db)):
    if not _social_enabled():
        raise HTTPException(503, "Social account management is disabled")
    _schema_ready(db)
    if provider not in PROVIDERS:
        raise HTTPException(404, "Provider not supported")
    user = identity[0]
    row = db.query(SocialAccount).filter_by(user_id=user.id,provider=provider).first()
    if not row:
        raise HTTPException(404, "Social identity not connected")
    remaining = db.query(SocialAccount).filter(
        SocialAccount.user_id==user.id, SocialAccount.id!=row.id).count()
    if not user.password_hash and remaining == 0:
        raise HTTPException(409, "Set a password or connect another provider before disconnecting your last sign-in method")
    db.delete(row);db.commit()
    return {"ok":True}
