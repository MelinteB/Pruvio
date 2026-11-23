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
