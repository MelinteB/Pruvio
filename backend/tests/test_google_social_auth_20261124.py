"""Regression checks for opt-in Google OIDC and Core phone enrollment."""
import importlib
import os
import pkgutil
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.db.database import Base
import app.models
for model in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module("app.models." + model.name)

from app.models.user import User
from app.models.social_identity import SocialAccount
from app.react_app import google_auth as oauth


def req(cookie="", method="POST"):
    h = [(b"cookie", cookie.encode())] if cookie else []
    return Request({"type":"http", "method":method, "path":"/api/v1/auth/social/complete",
                    "headers":h, "query_string":b"", "client":("127.0.0.1", 12345),
                    "scheme":"https", "server":("pruvs.io", 443)})


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path/"google_auth.sqlite"))
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", "test-standalone-google-oauth-secret-min-32-characters")
    monkeypatch.setenv("PRUVS_SOCIAL_LOGIN_ENABLED", "true")
    monkeypatch.setenv("PRUVS_SOCIAL_GOOGLE_ENABLED", "true")
    monkeypatch.setenv("PRUVS_SOCIAL_GOOGLE_CLIENT_ID", "fake-web-id.apps.googleusercontent.com")
    monkeypatch.setenv("PRUVS_SOCIAL_GOOGLE_CLIENT_SECRET", "unit-test-only")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pruvs.io")
    yield db
    db.close()
    engine.dispose()


def ticket(db, *, email="alice@example.org", subject="google-sub-123"):
    data = {"iat":int(time.time()), "provider":"google", "email":email,
            "subject":subject, "name":"Alice Example", "next":"/"}
    token = oauth._seal(data)
    return req("pruvs_google_pending=" + token)


def form(**overrides):
    payload = {"name":"Alice Example", "phone_country":"RO", "phone_number":"0722 123 456",
               "accepted_terms":True,"accepted_privacy":True}
    payload.update(overrides)
    return oauth.GoogleSignup(**payload)


def test_provider_order_and_google_only_if_explicitly_configured(database, monkeypatch):
    assert [p["id"] for p in oauth.providers(db=database)["providers"]][:3] == ["google","linkedin","yahoo"]
    assert [p["enabled"] for p in oauth.providers(db=database)["providers"]] == [True,False,False,False,False,False]
    monkeypatch.delenv("PRUVS_SOCIAL_GOOGLE_CLIENT_SECRET")
    assert not any(p["enabled"] for p in oauth.providers(db=database)["providers"])
    with pytest.raises(HTTPException) as exc:
        oauth._require_google(database)
    assert exc.value.status_code == 503


def test_state_tamper_expiry_and_safe_return(database):
    sealed = oauth._seal({"iat":int(time.time()),"state":"abc"})
    assert oauth._unseal(sealed,600)["state"] == "abc"
    with pytest.raises(HTTPException):
        oauth._unseal(sealed[:-1] + ("Z" if sealed[-1] != "Z" else "Q"),600)
    with pytest.raises(HTTPException):
        oauth._unseal(oauth._seal({"iat":int(time.time())-2000}),600)
    assert oauth._next("//external.com") == "/"
    assert oauth._next("/\\external") == "/"
    assert oauth._next("/projects/my-trip") == "/projects/my-trip"


def test_google_oidc_validated_nonce_email_and_subject(database, monkeypatch):
    class JWKS:
        def get_signing_key_from_jwt(self, _raw): return SimpleNamespace(key="unit-test-key")
    claims = {"iss":"https://accounts.google.com","aud":"client",
              "sub":"stable-google-sub","email":"alice@example.org",
              "email_verified":True,"name":"Alice","nonce":"correct",
              "exp":9999999999,"iat":123}
    monkeypatch.setattr(oauth.jwt,"PyJWKClient",lambda *_:JWKS())
    monkeypatch.setattr(oauth.jwt,"decode",lambda *_args,**_kwargs:claims)
    assert oauth._verify_google_id_token("fake.jwt.token","client","correct")["subject"] == "stable-google-sub"
    with pytest.raises(HTTPException):
        oauth._verify_google_id_token("fake.jwt.token","client","WRONG")
    claims["email_verified"] = False
    with pytest.raises(HTTPException):
        oauth._verify_google_id_token("fake.jwt.token","client","correct")


def test_google_signup_requires_phone_and_creates_unique_provider_identity(database):
    response = Response()
    result = oauth.complete(form(),ticket(database),response,db=database)
    assert result["user"]["email"] == "alice@example.org"
    assert result["user"]["phone_number"] == "+40722123456"
    user = database.query(User).filter_by(email="alice@example.org").one()
    assert user.is_email_verified is True
    assert user.is_phone_verified is False
    assert user.password_hash is None
    linked = database.query(SocialAccount).filter_by(user_id=user.id).one()
    assert (linked.provider,linked.subject) == ("google","google-sub-123")
    assert "pruvs_session=" in response.headers["set-cookie"] or "pruvs_google_pending=" in response.headers["set-cookie"]


def test_invalid_length_cannot_register_google_account(database):
    with pytest.raises(ValueError):
        oauth.complete(form(phone_number="0722 123"),ticket(database),Response(),db=database)
    assert database.query(User).count() == 0


def test_consent_is_not_optional(database):
    with pytest.raises(HTTPException) as exc:
        oauth.complete(form(accepted_privacy=False),ticket(database),Response(),db=database)
    assert exc.value.status_code == 422
    assert database.query(User).count() == 0


def test_matching_email_must_not_take_over_existing_pruvs_user(database):
    old = User(name="Existing",email="alice@example.org",phone_number="+40723123456",
               username="existing.user",username_key="existing.user",status="active",
               is_email_verified=True)
    database.add(old);database.commit()
    with pytest.raises(HTTPException) as exc:
        oauth.complete(form(),ticket(database),Response(),db=database)
    assert exc.value.status_code == 409
    assert database.query(SocialAccount).count() == 0


def test_google_login_uses_provider_subject_not_matching_email(database,monkeypatch):
    old = User(name="Linked",email="alice@example.org",phone_number="+40723123456",
               username="linked.user",username_key="linked.user",status="active",
               is_email_verified=True)
    database.add(old);database.flush()
    database.add(SocialAccount(user_id=old.id,provider="google",subject="subject-A"))
    database.commit()
    monkeypatch.setattr(oauth,"_exchange_code",lambda *_args: {
        "subject":"subject-A","name":"Linked","email":"changed@example.org"})
    flow = {"iat":int(time.time()),"mode":"login","state":"test-state","verifier":"verifier",
            "nonce":"nonce","next":"/inbox","uid":None,"session_hash":""}
    token = oauth._seal(flow)
    request = req("pruvs_google_flow=" + token,method="GET")
    response = oauth.callback(request, code="valid-code",state="test-state",db=database)
    assert response.status_code == 303
    assert response.headers["location"] == "/inbox"
    assert old.id == database.query(SocialAccount).filter_by(subject="subject-A").one().user_id


def test_google_linking_other_users_identity_is_forbidden(database,monkeypatch):
    # A client must already be authenticated to request mode=link.
    with pytest.raises(HTTPException) as exc:
        oauth.start(req(method="GET"),mode="link",db=database)
    assert exc.value.status_code == 401
