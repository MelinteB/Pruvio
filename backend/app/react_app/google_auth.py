"""Pruvs Core Google OIDC: verified subject login and mandatory phone enrollment.

Only Google is implemented and may be enabled. All other social UI choices
remain disabled until their own independently reviewed provider integrations.
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
from app.react_app.auth import COOKIE, current, digest, issue, limit
from app.services.phone_numbers import normalize_signup_phone
from app.services.username_service import derive_available_username, check_username_available
from app.usernames import username_key

router = APIRouter(prefix="/api/v1/auth/social", tags=["Pruvs Core Google login"])
GOOGLE = "google"
PROVIDERS = ("google", "linkedin", "yahoo", "facebook", "instagram", "tiktok")
STATE_COOKIE = "pruvs_google_flow"
PENDING_COOKIE = "pruvs_google_pending"
COOKIE_PATH = "/api/v1/auth/social"


class GoogleSignup(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    username: str | None = Field(default=None, max_length=80)
    phone_country: str = Field(default="RO", min_length=2, max_length=2)
    phone_number: str = Field(min_length=4, max_length=48)
    accepted_terms: bool
    accepted_privacy: bool
    marketing_opt_in: bool = False
    notifications_opt_in: bool = False


def _state_secret() -> bytes:
    secret = os.getenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Google sign-in state secret is not configured")
    return secret.encode("utf-8")


def _configured() -> bool:
    return all((
        os.getenv("PRUVS_SOCIAL_LOGIN_ENABLED", "false").lower() == "true",
        os.getenv("PRUVS_SOCIAL_GOOGLE_ENABLED", "false").lower() == "true",
        bool(os.getenv("PRUVS_SOCIAL_GOOGLE_CLIENT_ID", "").strip()),
        bool(os.getenv("PRUVS_SOCIAL_GOOGLE_CLIENT_SECRET", "").strip()),
        len(os.getenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", "")) >= 32,
    ))


def _schema_ready(db) -> bool:
    return inspect(db.get_bind()).has_table(SocialAccount.__tablename__)


def _require_google(db):
    if not _configured() or not _schema_ready(db):
        raise HTTPException(503, "Google sign-in is not yet configured")


def _origin() -> str:
    raw = os.getenv("PUBLIC_BASE_URL", "https://pruvs.io").strip().rstrip("/")
    value = urlparse(raw)
    if (value.scheme != "https" or not value.hostname or
            value.username or value.password or value.path or value.query or value.fragment):
        raise HTTPException(503, "An exact HTTPS PUBLIC_BASE_URL is required for Google sign-in")
    return raw


def _callback_url() -> str:
    return _origin() + "/api/v1/auth/social/google/callback"


def _next(value: str) -> str:
    if (not isinstance(value, str) or not value.startswith("/") or value.startswith("//")
            or "\\" in value or any(ord(ch) < 32 for ch in value)):
        return "/"
    return value


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _seal(body: dict) -> str:
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    signature = _b64(hmac.new(_state_secret(), raw.encode(), hashlib.sha256).digest())
    return raw + "." + signature


def _unseal(value: str, max_age: int) -> dict:
    try:
        raw, signature = value.split(".", 1)
        expected = _b64(hmac.new(_state_secret(), raw.encode(), hashlib.sha256).digest())
        if not secrets.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        elapsed = int(time.time()) - int(body["iat"])
        if elapsed < -30 or elapsed > max_age:
            raise ValueError("expired")
        return body
    except (ValueError, KeyError, TypeError, OverflowError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(400, "Google sign-in expired. Try again.") from None


def _cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(name, value, httponly=True, secure=True, samesite="lax",
                        max_age=max_age, path=COOKIE_PATH)


def _clear(response: Response, name: str) -> None:
    response.delete_cookie(name, secure=True, httponly=True, samesite="lax", path=COOKIE_PATH)


def _verify_google_id_token(token: str, client_id: str, nonce: str) -> dict:
    """Verify Google's signature and OIDC assertions, never trust client claims."""
    if not isinstance(token, str) or len(token) > 12000:
        raise HTTPException(502, "Google did not provide a valid ID token")
    try:
        key = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs").get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, key.key, algorithms=["RS256"],
            audience=client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            leeway=30,
        )
        if not secrets.compare_digest(str(claims.get("nonce") or ""), nonce):
            raise ValueError("nonce mismatch")
    except (jwt.PyJWTError, ValueError, TypeError, OSError):
        raise HTTPException(502, "Google identity verification failed") from None
    subject = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").strip().lower()
    verified = claims.get("email_verified") is True or claims.get("email_verified") == "true"
    if (not subject or len(subject) > 255 or not verified or
            len(email) > 255 or "@" not in email):
        raise HTTPException(403, "Google did not provide a verified email address")
    name = " ".join(str(claims.get("name") or "").split())[:255]
    return {"provider":GOOGLE, "subject":subject, "email":email,
            "name":name or email.split("@")[0]}


def _exchange_code(code: str, verifier: str, nonce: str) -> dict:
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":os.environ["PRUVS_SOCIAL_GOOGLE_CLIENT_ID"],
                "client_secret":os.environ["PRUVS_SOCIAL_GOOGLE_CLIENT_SECRET"],
                "code":code,
                "code_verifier":verifier,
                "redirect_uri":_callback_url(),
                "grant_type":"authorization_code",
            }, timeout=8, follow_redirects=False,
        )
        if response.status_code != 200 or len(response.content) > 65536:
            raise ValueError("bad token response")
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("invalid payload")
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Google authentication is temporarily unavailable") from None
    return _verify_google_id_token(
        data.get("id_token"), os.environ["PRUVS_SOCIAL_GOOGLE_CLIENT_ID"], nonce,
    )


@router.get("/providers")
def providers(db=Depends(get_db)):
    ready = _configured() and _schema_ready(db)
    return {"providers": [{"id":provider, "enabled": ready if provider == GOOGLE else False}
                          for provider in PROVIDERS]}


@router.get("/google/start")
def start(request: Request, mode: str = Query("login", pattern="^(login|link)$"),
          next: str = "/", db=Depends(get_db)):
    _require_google(db)
    limit(db, request, "google-oidc-start", 20)
    link_user_id, link_session_hash = None, ""
    if mode == "link":
        user, _session = current(request, db)
        link_user_id = user.id
        link_session_hash = digest(request.cookies.get(COOKIE, ""))
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    flow = {"iat":int(time.time()), "state":state, "nonce":nonce,
            "verifier":verifier, "mode":mode, "next":_next(next),
            "uid":link_user_id, "session_hash":link_session_hash}
    params = {
        "client_id":os.environ["PRUVS_SOCIAL_GOOGLE_CLIENT_ID"],
        "redirect_uri":_callback_url(),
        "response_type":"code",
        "state":state,
        "nonce":nonce,
        "scope":"openid email profile",
        "code_challenge":_b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method":"S256",
        "prompt":"select_account",
    }
    response = RedirectResponse(
        "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params), status_code=302)
    _cookie(response, STATE_COOKIE, _seal(flow), 600)
    return response


@router.get("/google/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = "",
             db=Depends(get_db)):
    _require_google(db)
    flow = _unseal(request.cookies.get(STATE_COOKIE, ""), 600)
    if not state or not secrets.compare_digest(str(flow.get("state") or ""), state):
        raise HTTPException(400, "Google login state mismatch")
    if error or not code or len(code) > 2048:
        response = RedirectResponse("/login?social_error=cancelled", status_code=303)
        _clear(response, STATE_COOKIE)
        return response
    identity = _exchange_code(code, flow["verifier"], flow["nonce"])
    existing = db.query(SocialAccount).filter_by(provider=GOOGLE, subject=identity["subject"]).first()
    if flow["mode"] == "link":
        user, _ = current(request, db)
        if (user.id != flow.get("uid") or not secrets.compare_digest(
                digest(request.cookies.get(COOKIE, "")), flow.get("session_hash", ""))):
            raise HTTPException(403, "Google linking session has changed")
        if existing and existing.user_id != user.id:
            raise HTTPException(409, "This Google account is connected to a different Pruvs user")
        other = db.query(SocialAccount).filter_by(provider=GOOGLE, user_id=user.id).first()
        if other and (not existing or other.id != existing.id):
            raise HTTPException(409, "Disconnect the previous Google account before linking another")
        if not existing:
            db.add(SocialAccount(user_id=user.id, provider=GOOGLE,
                                 subject=identity["subject"], display_name=identity["name"]))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, "Google account is already linked") from None
        response = RedirectResponse("/account", status_code=303)
        _clear(response, STATE_COOKIE)
        return response
    if existing:
        user = db.get(User, existing.user_id)
        if not user or user.status != "active":
            raise HTTPException(403, "Pruvs account is unavailable")
        existing.last_used_at = datetime.utcnow()
        response = RedirectResponse(_next(flow.get("next")), status_code=303)
        issue(db, user, request, response)
        _clear(response, STATE_COOKIE)
        return response
    pending = {
        "iat":int(time.time()),"provider":GOOGLE,"subject":identity["subject"],
        "name":identity["name"],"email":identity["email"],"next":_next(flow.get("next")),
    }
    response = RedirectResponse("/register?social=pending&next=" + quote(_next(flow.get("next")), safe=""), status_code=303)
    _cookie(response, PENDING_COOKIE, _seal(pending), 900)
    _clear(response, STATE_COOKIE)
    return response


@router.get("/pending")
def pending(request: Request, db=Depends(get_db)):
    _require_google(db)
    ticket = _unseal(request.cookies.get(PENDING_COOKIE, ""), 900)
    if ticket.get("provider") != GOOGLE or not ticket.get("email"):
        raise HTTPException(400, "Google registration session is invalid")
    return {"provider":GOOGLE, "can_complete":True, "name":ticket.get("name") or "",
            "email":ticket["email"]}


@router.post("/complete")
def complete(data: GoogleSignup, request: Request, response: Response, db=Depends(get_db)):
    _require_google(db)
    limit(db, request, "google-oidc-complete", 10)
    if request.cookies.get(COOKIE):
        raise HTTPException(409, "Sign out first, or connect Google from your Pruvs account")
    ticket = _unseal(request.cookies.get(PENDING_COOKIE, ""), 900)
    if ticket.get("provider") != GOOGLE or not ticket.get("email") or not ticket.get("subject"):
        raise HTTPException(400, "Google registration session is invalid")
    if not (data.accepted_terms and data.accepted_privacy):
        raise HTTPException(422, "You must accept Terms and Privacy Notice")
    email = str(ticket["email"]).strip().lower()
    if db.query(User.id).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "This email has a Pruvs account. Sign in and connect Google in Account.")
    if db.query(SocialAccount.id).filter_by(provider=GOOGLE, subject=ticket["subject"]).first():
        raise HTTPException(409, "Google identity is already connected")
    phone = normalize_signup_phone(data.phone_number, data.phone_country)
    if db.query(User.id).filter_by(phone_number=phone).first():
        raise HTTPException(409, "This phone number is already registered")
    name = " ".join(data.name.split()).strip()
    if len(name) < 2:
        raise HTTPException(422, "Your full name is required")
    username = (check_username_available(db, data.username) if data.username
                else derive_available_username(db, name))
    now = datetime.utcnow()
    user = User(
        phone_number=phone,name=name,email=email,status="active",
        username=username,username_key=username_key(username),password_hash=None,
        is_email_verified=True,is_phone_verified=False,
        accepted_terms=True,accepted_terms_at=now,terms_version=TERMS_VERSION,
        accepted_privacy=True,accepted_privacy_at=now,privacy_version=PRIVACY_VERSION,
        marketing_opt_in=data.marketing_opt_in,
        notifications_opt_in=data.notifications_opt_in,
        updated_at=now,last_seen_at=now,
    )
    try:
        db.add(user)
        db.flush()
        db.add(SocialAccount(user_id=user.id,provider=GOOGLE,
                             subject=ticket["subject"],display_name=ticket.get("name", "")[:255]))
        db.flush()
        result = issue(db, user, request, response)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email, phone or Google identity is already registered") from None
    _clear(response, PENDING_COOKIE)
    return result


@router.get("/accounts")
def accounts(identity=Depends(current), db=Depends(get_db)):
    if not _schema_ready(db):
        return {"accounts":[]}
    rows = db.query(SocialAccount).filter_by(user_id=identity[0].id).all()
    return {"accounts":[{"provider":item.provider,"name":item.display_name}
                        for item in rows]}
