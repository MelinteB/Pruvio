"""Run with: python -m pytest tests/test_device_otp.py -q (no real messages)."""
import hashlib
import hmac
import importlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import database
from app.db.database import Base, get_db

for model_file in (Path(__file__).parents[1] / "app/models").glob("*.py"):
    importlib.import_module("app.models." + model_file.stem)

from app.models.user import User
from app.models.verification_code import VerificationCode
from app.models.trusted_device import TrustedDevice
from app.services import onboarding_otp_service as otp
from app.services import phone_otp_service as phone
from app.services import trusted_device_service as devices
from app.services.account_service import confirm_password_reset, request_password_reset
from app.services.auth_service import start_passwordless_login, complete_passwordless_login
from app.services.password_service import hash_password
from app.api.trusted_device import router as device_router
from app.api.account import router as account_router


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("OTP_SECRET", "test-secret-for-otp-only-" + "a" * 32)
    monkeypatch.setenv("OTP_DEBUG_RETURN_CODE", "true")
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("WHATSAPP_OTP_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "test-phone-id")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test-verify-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pruvio.test")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        user = User(username="Test User", username_key="test user", name="Test User", email="test@example.com", phone_number="+40711111111", status="active",
                    is_phone_verified=True, is_email_verified=True, accepted_terms=True, accepted_privacy=True,
                    password_hash=hash_password("testing-password"))
        session.add(user)
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def delivery(monkeypatch):
    wa = Mock(return_value={"sent": True, "provider": "whatsapp", "status": "queued", "message_id": "wamid.test"})
    sms = Mock(return_value={"sent": True, "provider": "twilio", "status": "queued", "message_id": "SMtest"})
    email = Mock(return_value={"sent": True, "provider": "resend", "status": "queued"})
    monkeypatch.setattr(phone, "send_whatsapp_otp", wa)
    monkeypatch.setattr(phone, "send_sms_verification_code", sms)
    monkeypatch.setattr(otp, "send_email_verification_code", email)
    return wa, sms, email


def user(db):
    return db.query(User).first()


def client(db):
    app = FastAPI()
    app.include_router(device_router, prefix="/auth")
    app.include_router(account_router, prefix="/auth")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, base_url="https://pruvio.test")


















def test_login_otp_challenge_bound_and_single_use(db, delivery):
    account = user(db)
    result = start_passwordless_login(db, account.email)
    with pytest.raises(ValueError):
        complete_passwordless_login(db, account.email, result["debug_otp"], challenge_id="wrong-browser-challenge")
    verified = complete_passwordless_login(db, account.email, result["debug_otp"], challenge_id=result["challenge_id"])
    assert verified.id == account.id
    with pytest.raises(ValueError):
        complete_passwordless_login(db, account.email, result["debug_otp"], challenge_id=result["challenge_id"])


def test_attempt_limit_and_expiry(db, delivery):
    result = start_passwordless_login(db, user(db).email)
    wrong = "000000"
    for _ in range(5):
        with pytest.raises(ValueError):
            complete_passwordless_login(db, user(db).email, wrong, challenge_id=result["challenge_id"])
    with pytest.raises(ValueError):
        complete_passwordless_login(db, user(db).email, result["debug_otp"], challenge_id=result["challenge_id"])
    assert db.query(VerificationCode).first().status == "failed"
    result = start_passwordless_login(db, user(db).email)
    row = db.query(VerificationCode).filter_by(challenge_id=result["challenge_id"]).one()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(ValueError, match="expired"):
        complete_passwordless_login(db, user(db).email, result["debug_otp"], challenge_id=result["challenge_id"])


def test_trusted_device_rejects_otp_and_is_account_bound(db, delivery):
    account = user(db)
    result = start_passwordless_login(db, account.email)
    claim = devices.create_device_claim(db, account)
    token = devices.consume_device_claim(db, claim)
    assert devices.is_trusted_device(db, account, token)
    assert not devices.is_trusted_device(db, account, "forged-cookie")
    with pytest.raises(ValueError, match="already verified"):
        start_passwordless_login(db, account.email, device_token=token)
    with pytest.raises(ValueError, match="already verified"):
        complete_passwordless_login(db, account.email, result["debug_otp"], challenge_id=result["challenge_id"], device_token=token)
    other = User(phone_number="+40722222222", email="other@example.com", status="active")
    db.add(other); db.commit()
    assert not devices.is_trusted_device(db, other, token)
    record = db.query(TrustedDevice).first()
    record.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert not devices.is_trusted_device(db, account, token)
    start_passwordless_login(db, account.email, device_token=token)


def test_remember_route_cookie_single_use_and_expired_grants(db):
    claim = devices.create_device_claim(db, user(db))
    with client(db) as api:
        response = api.post("/auth/device/remember", json={"claim": claim})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        token = api.cookies.get(devices.DEVICE_COOKIE)
        assert devices.is_trusted_device(db, user(db), token)
        assert api.post("/auth/device/remember", json={"claim": claim}).status_code == 400
    claim = devices.create_device_claim(db, user(db))
    row = db.query(TrustedDevice).filter(TrustedDevice.claim_hash.is_not(None)).one()
    row.claim_expires_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
    with pytest.raises(ValueError):
        devices.consume_device_claim(db, claim)


def test_api_password_requires_otp_for_new_browser(db):
    with client(db) as api:
        payload = {"identifier": user(db).email, "password": "testing-password"}
        assert api.post("/auth/password/login", json=payload).json()["otp_required"] is True
        claim = devices.create_device_claim(db, user(db))
        api.post("/auth/device/remember", json={"claim": claim})
        assert api.post("/auth/password/login", json=payload).json()["otp_required"] is False
        assert api.post("/auth/password/login", json={**payload, "password": "wrong"}).status_code == 400


def test_password_reset_revokes_device_trust(db, delivery):
    account = user(db)
    token = devices.consume_device_claim(db, devices.create_device_claim(db, account))
    result = request_password_reset(db, account.email)
    confirm_password_reset(db, account.email, result["debug_otp"], "new-test-password")
    assert not devices.is_trusted_device(db, account, token)




def test_resend_invalidates_old_code_and_cooldown(db, delivery, monkeypatch):
    first = start_passwordless_login(db, user(db).email)
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "60")
    with pytest.raises(ValueError, match="wait"):
        start_passwordless_login(db, user(db).email)
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
    second = start_passwordless_login(db, user(db).email)
    with pytest.raises(ValueError):
        complete_passwordless_login(db, user(db).email, first["debug_otp"], challenge_id=first["challenge_id"])
    complete_passwordless_login(db, user(db).email, second["debug_otp"], challenge_id=second["challenge_id"])


def test_compatibility_migration_preserves_old_codes(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE verification_codes (id INTEGER PRIMARY KEY, code_hash VARCHAR NOT NULL)"))
        conn.execute(text("INSERT INTO verification_codes VALUES (1, 'existing-hash')"))
    monkeypatch.setattr(database, "engine", engine)
    database.ensure_compatibility_schema()
    database.ensure_compatibility_schema()
    assert "challenge_id" in {c["name"] for c in inspect(engine).get_columns("verification_codes")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT code_hash FROM verification_codes WHERE id=1")).scalar() == "existing-hash"


def test_email_https_delivery_and_failures(db, monkeypatch):
    from app.services import email_service
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_FROM", "Pruvs <verify@example.com>")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pruvs.io")
    captured = []
    def reply(request):
        captured.append(request)
        return httpx.Response(200, json={"id": "email.test"})
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(reply), trust_env=False, **kw))
    result = email_service.send_email_verification_code("test@example.com", "123456", 10)
    assert result["sent"] and result["status"] == "queued"
    assert captured[0].url == "https://api.resend.com/emails"
    payload = json.loads(captured[0].content)
    assert payload["to"] == ["test@example.com"] and "123456" in payload["text"]
    assert "123456" in payload["html"]
    assert 'https://pruvs.io/static/pruvs-logo.png' in payload["html"]
    assert payload["subject"] == "Your Pruvs verification code"
    monkeypatch.delenv("RESEND_API_KEY")
    assert not email_service.send_email_verification_code("test@example.com", "123456", 10)["sent"]






def test_revoked_and_blocked_device_claims_cannot_be_used(db):
    account = user(db)
    claim = devices.create_device_claim(db, account)
    devices.revoke_trusted_devices(db, account.id); db.commit()
    with pytest.raises(ValueError):
        devices.consume_device_claim(db, claim)
    claim = devices.create_device_claim(db, account)
    account.status = "blocked"; db.commit()
    with pytest.raises(ValueError):
        devices.consume_device_claim(db, claim)


def test_debug_code_not_returned_in_production(db, delivery, monkeypatch):
    monkeypatch.setenv("OTP_DEBUG_RETURN_CODE", "false")
    result = start_passwordless_login(db, user(db).email)
    assert result["debug_otp"] is None
    assert "code_ciphertext" not in result and "code_hash" not in result


def test_password_reset_expires_outstanding_login_codes(db, delivery):
    account = user(db)
    login = start_passwordless_login(db, account.email)
    reset = request_password_reset(db, account.email)
    confirm_password_reset(db, account.email, reset["debug_otp"], "new-test-password")
    with pytest.raises(ValueError):
        complete_passwordless_login(db, account.email, login["debug_otp"], challenge_id=login["challenge_id"])


def test_registration_does_not_reactivate_blocked_or_trust_changed_phone(db, delivery):
    account = user(db)
    account.status = "blocked"; db.commit()
    with pytest.raises(ValueError, match="unavailable"):
        otp.start_registration(db, phone_number=account.phone_number, email=account.email, display_name="Test", accepted_terms=True, accepted_privacy=True)
    account.status = "pending_join"; db.commit()
    otp.create_or_update_registration_user(db, phone_number="+40799999999", email=account.email,
                                          display_name="Test", accepted_terms=True, accepted_privacy=True)
    assert not account.is_phone_verified


def test_current_device_account_route_tracks_the_browser_cookie(db):
    account = user(db)
    claim = devices.create_device_claim(db, account)
    with client(db) as api:
        assert api.get('/auth/device/current').json() == {'user_id': None}
        remembered = api.post('/auth/device/remember', json={'claim': claim})
        assert remembered.status_code == 200
        assert api.get('/auth/device/current').json() == {'user_id': account.id}
        api.cookies.set(devices.DEVICE_COOKIE, 'forged-cookie')
        assert api.get('/auth/device/current').json() == {'user_id': None}
