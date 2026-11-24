"""Regression: Google short env group controls readiness, registration and linking.

No network or production database needed. Other social providers remain gated
behind the older feature switch and cannot be enabled by GOOGLE_ENABLED.
"""
import importlib
import os
import pkgutil
import time

import app.models
import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

for module in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module("app.models." + module.name)

from app.db.database import Base
from app.models.social_identity import SocialAccount
from app.models.user import User
from app.react_app import social_auth as social


def _request(token=None):
    headers = [(b"cookie", (social.SIGNUP_COOKIE + "=" + token).encode())] if token else []
    return Request({"type": "http", "method": "POST",
                    "path": "/api/v1/auth/social/complete",
                    "query_string": b"", "headers": headers,
                    "client": ("127.0.0.1", 54321),
                    "scheme": "https", "server": ("pruvs-core-staging.onrender.com", 443)})


@pytest.fixture
def ready_db(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-secret-not-real")
    monkeypatch.delenv("PRUVS_SOCIAL_LOGIN_ENABLED", raising=False)
    monkeypatch.delenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", raising=False)
    monkeypatch.delenv("PRUVS_SOCIAL_YAHOO_ENABLED", raising=False)
    engine = create_engine("sqlite:///" + str(tmp_path / "social-ready.sqlite"))
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _pending(email="new.google@example.org"):
    return social._seal({
        "iat": int(time.time()), "provider": "google", "subject": "google-test-sub",
        "email": email, "verified": True, "name": "Google Test Guest", "next": "/"
    })


def test_google_enabled_without_old_global_switch(ready_db):
    result = social.providers(db=ready_db)
    providers = {item["id"]: item for item in result["providers"]}
    assert providers["google"]["enabled"] is True
    assert providers["yahoo"]["enabled"] is False
    assert providers["facebook"]["enabled"] is False


def test_google_disabled_when_flag_is_false(ready_db, monkeypatch):
    monkeypatch.setenv("GOOGLE_ENABLED", "false")
    providers = {item["id"]: item for item in social.providers(db=ready_db)["providers"]}
    assert providers["google"]["enabled"] is False


def test_google_pending_enrollment_works_without_old_global_switch(ready_db):
    result = social.pending(_request(_pending()), db=ready_db)
    assert result["provider"] == "google"
    assert result["can_complete"] is True
    assert result["email"] == "new.google@example.org"


def test_google_signup_accepts_required_country_phone_without_old_global_switch(ready_db):
    data = social.CompleteSignup(
        name="Google Test Guest",
        phone_number="0722 123 456",
        phone_country="RO",
        accepted_terms=True,
        accepted_privacy=True,
    )
    response = Response()
    result = social.complete(data, _request(_pending()), response, db=ready_db)
    assert result["user"]["phone_number"] == "+40722123456"
    user = ready_db.query(User).filter_by(email="new.google@example.org").one()
    assert user.is_email_verified is True
    assert user.is_phone_verified is False
    link = ready_db.query(SocialAccount).filter_by(user_id=user.id).one()
    assert link.provider == "google"
    assert link.subject == "google-test-sub"


def test_other_provider_stays_disabled_even_when_google_enabled(ready_db):
    with pytest.raises(HTTPException) as err:
        social._ensure_provider("yahoo")
    assert err.value.status_code == 503
