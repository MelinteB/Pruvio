"""Core social authentication security regression tests (no network needed)."""
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.social_identity import SocialAccount
from app.models.user import User
from app.react_app import social_auth as social


def test_social_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PRUVS_SOCIAL_LOGIN_ENABLED", raising=False)
    monkeypatch.setenv("PRUVS_SOCIAL_GOOGLE_CLIENT_ID","test-client")
    monkeypatch.setenv("PRUVS_SOCIAL_GOOGLE_CLIENT_SECRET","test-secret")
    monkeypatch.setenv("PRUVS_SOCIAL_GOOGLE_ENABLED","true")
    monkeypatch.setenv("PRUVS_SOCIAL_AUTH_STATE_SECRET","x"*40)
    assert not social._configured("google")


def test_signed_state_rejects_tamper_and_expiry(monkeypatch):
    monkeypatch.setenv("PRUVS_SOCIAL_AUTH_STATE_SECRET","x"*40)
    body={"iat":int(time.time()),"state":"abc","provider":"google"}
    ticket=social._seal(body)
    assert social._unseal(ticket,max_age=600)==body
    with pytest.raises(HTTPException):
        social._unseal(ticket[:-2]+"zz",max_age=600)
    old=social._seal({"iat":int(time.time())-901,"state":"old"})
    with pytest.raises(HTTPException):
        social._unseal(old,max_age=600)


def test_never_redirect_externally():
    assert social._internal_next("https://evil.test") == "/"
    assert social._internal_next("//evil.test") == "/"
    assert social._internal_next("/\\evil.test") == "/"
    assert social._internal_next("/bills") == "/bills"


def test_oidc_requires_signed_token_verified_email_and_matching_nonce(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    now=datetime.now(timezone.utc)
    claims={"iss":"https://accounts.google.com","aud":"client-123",
            "sub":"opaque-user-sub","email":"reader@example.test",
            "email_verified":True,"name":"Reader",
            "nonce":"unique-state","iat":now,"exp":now+timedelta(minutes=10)}
    raw=jwt.encode(claims,key,algorithm="RS256")
    monkeypatch.setattr(social.jwt,"PyJWKClient",
        lambda uri: SimpleNamespace(get_signing_key_from_jwt=lambda token:SimpleNamespace(key=key.public_key())))
    result=social._oidc_identity("google",{"id_token":raw},"client-123","unique-state")
    assert result["subject"]=="opaque-user-sub"
    assert result["verified"] is True
    with pytest.raises(HTTPException):
        social._oidc_identity("google",{"id_token":raw},"client-123","wrong-nonce")
    with pytest.raises(HTTPException):
        social._oidc_identity("google",{"id_token":raw},"other-app","unique-state")


def test_provider_subject_unique_and_not_email_derived():
    import app.models
    engine=create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user=User(id=1,phone_number="+40000000000",username="reader",
                  username_key="reader",name="Reader",email="reader@example.test",
                  status="active",is_email_verified=True)
        db.add(user);db.flush()
        db.add(SocialAccount(user_id=user.id,provider="google",
                             subject="provider-only-sub",display_name="Reader"))
        db.commit()
        row=db.query(SocialAccount).first()
        assert row.subject=="provider-only-sub"
        assert row.subject!=user.email


def test_apple_requires_full_staging_configuration(monkeypatch):
    monkeypatch.setenv("PRUVS_SOCIAL_LOGIN_ENABLED", "true")
    monkeypatch.setenv("PRUVS_SOCIAL_APPLE_ENABLED", "true")
    monkeypatch.setenv("PRUVS_SOCIAL_APPLE_CLIENT_ID", "io.pruvs.staging")
    monkeypatch.setenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", "k"*40)
    for key in ("PRUVS_SOCIAL_APPLE_TEAM_ID", "PRUVS_SOCIAL_APPLE_KEY_ID",
                "PRUVS_SOCIAL_APPLE_PRIVATE_KEY_BASE64"):
        monkeypatch.delenv(key, raising=False)
    assert not social._configured("apple")


def test_apple_web_client_secret_is_es256_signed(monkeypatch):
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    monkeypatch.setenv("PRUVS_SOCIAL_APPLE_PRIVATE_KEY_BASE64",
                       base64.b64encode(pem).decode())
    monkeypatch.setenv("PRUVS_SOCIAL_APPLE_TEAM_ID", "MYTEAMID09")
    monkeypatch.setenv("PRUVS_SOCIAL_APPLE_KEY_ID", "MYKEYID123")
    token = social._apple_client_secret("io.pruvs.staging")
    claims = jwt.decode(token, key.public_key(), algorithms=["ES256"],
                        audience="https://appleid.apple.com",
                        options={"require":["iss", "aud", "sub", "iat", "exp"]})
    assert claims["iss"] == "MYTEAMID09"
    assert claims["sub"] == "io.pruvs.staging"
    assert jwt.get_unverified_header(token)["kid"] == "MYKEYID123"
    assert 0 < claims["exp"] - claims["iat"] <= 86400*7


def test_apple_oidc_checks_issuer_audience_nonce_and_email_verification(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    now = datetime.now(timezone.utc)
    claims = {"iss":"https://appleid.apple.com", "aud":"io.pruvs.staging",
              "sub":"apple-subject-opaque", "email":"relay@privaterelay.appleid.com",
              "email_verified":"true", "nonce":"apple-test-nonce",
              "iat":now, "exp":now+timedelta(minutes=3)}
    raw = jwt.encode(claims,key,algorithm="RS256")
    monkeypatch.setattr(social.jwt,"PyJWKClient",
        lambda uri: SimpleNamespace(get_signing_key_from_jwt=
            lambda token:SimpleNamespace(key=key.public_key())))
    result = social._oidc_identity("apple",{"id_token":raw},
                                   "io.pruvs.staging","apple-test-nonce")
    assert result["subject"] == "apple-subject-opaque"
    assert result["verified"] is True
    with pytest.raises(HTTPException):
        social._oidc_identity("apple", {"id_token":raw},
                              "io.pruvs.staging", "wrong-nonce")
    with pytest.raises(HTTPException):
        social._oidc_identity("apple", {"id_token":raw},
                              "io.other.client", "apple-test-nonce")


def test_apple_formpost_cookie_is_separate_from_session(monkeypatch):
    from fastapi.responses import RedirectResponse
    monkeypatch.setenv("PUBLIC_BASE_URL","https://pruvs-core-staging.onrender.com")
    response = RedirectResponse("/api/v1/auth/social/apple/callback")
    social._cookie(response, social.STATE_COOKIE, "test-token", 600, apple_post=True)
    cookie = response.headers["set-cookie"].lower()
    assert "samesite=none" in cookie
    assert "secure" in cookie
    assert "httponly" in cookie
    assert social.STATE_COOKIE in cookie
    assert social.COOKIE not in cookie


def test_apple_callback_routes_registered():
    paths = {(route.path, tuple(sorted(route.methods or ()))) for route in social.router.routes}
    assert ("/api/v1/auth/social/{provider}/callback", ("POST",)) in paths
    assert ("/api/v1/auth/social/apple/finish", ("GET",)) in paths
