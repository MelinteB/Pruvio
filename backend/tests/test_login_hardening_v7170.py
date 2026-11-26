"""Core and Business login controls, isolated SQLite ORM databases."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.react_session import ReactRateLimit
from app.react_app.auth import limit
from business import login_security as login
from business import security
from business.merchant_enrollment import MerchantSignupRate
from business.models import Merchant, Staff

SECRET = "test-only-business-signing-key-" + "x" * 40

def request(ip="192.0.2.1"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))

@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(login, "get_settings", lambda: SimpleNamespace(business_jwt_secret=SECRET))
    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(business_jwt_secret=SECRET))
    engine = create_engine("sqlite://")
    for model in (ReactRateLimit, Merchant, Staff, MerchantSignupRate):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()

def test_core_limit_persisted_and_rejects(db):
    for _ in range(3):
        limit(db, request(), "test-login", 3)
    with pytest.raises(HTTPException) as exc:
        limit(db, request(), "test-login", 3)
    assert exc.value.status_code == 429
    row = db.scalars(select(ReactRateLimit)).one()
    assert row.count == 3
    row.reset_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    limit(db, request(), "test-login", 3)
    db.refresh(row)
    assert row.count == 1

def test_merchant_account_limit_across_ips(db):
    for i in range(login.ACCOUNT_LIMIT):
        login.consume_attempts(db, "user@example.test", "192.0.2." + str(i))
    with pytest.raises(HTTPException) as exc:
        login.consume_attempts(db, "user@example.test", "192.0.2.99")
    assert exc.value.status_code == 429
    assert all("@" not in row.bucket_hash for row in db.scalars(select(MerchantSignupRate)))

def test_merchant_ip_limit_across_accounts(db):
    for i in range(login.IP_LIMIT):
        login.consume_attempts(db, str(i) + "@example.test", "192.0.2.1")
    with pytest.raises(HTTPException) as exc:
        login.consume_attempts(db, "other@example.test", "192.0.2.1")
    assert exc.value.status_code == 429

def test_merchant_limit_expires(db):
    now = datetime.utcnow()
    for _ in range(login.ACCOUNT_LIMIT):
        login.consume_attempts(db, "a@example.test", "192.0.2.1", now=now)
    login.consume_attempts(db, "a@example.test", "192.0.2.1", now=now+timedelta(minutes=16))
    assert all(row.attempts == 1 for row in db.scalars(select(MerchantSignupRate)))

def test_failed_login_persists_and_no_account_disclosure(db):
    for email in ("missing@example.test", "blocked@example.test"):
        with pytest.raises(HTTPException) as exc:
            login.authenticate_merchant(SimpleNamespace(email=email,password="wrong"), request(), db)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid credentials"
    assert sum(row.attempts for row in db.scalars(select(MerchantSignupRate))) == 4

def test_existing_merchant_and_role_change(db):
    merchant=Merchant(name="Test",status="active")
    db.add(merchant);db.flush()
    staff=Staff(merchant_id=merchant.id,email="owner@example.test",
                password_hash=security.hasher.hash("correct test password"),role="owner",active=True)
    db.add(staff);db.commit()
    result=login.authenticate_merchant(SimpleNamespace(email=" OWNER@example.test ",password="correct test password"),request(),db)
    credentials=HTTPAuthorizationCredentials(scheme="Bearer",credentials=result["access_token"])
    assert security.merchant_actor(credentials,db).id==staff.id
    staff.role="manager";db.commit()
    with pytest.raises(HTTPException) as exc:
        security.merchant_actor(credentials,db)
    assert exc.value.status_code==401
    token=security.encode_merchant_token(staff)
    merchant.status="suspended";db.commit()
    with pytest.raises(HTTPException) as exc:
        security.merchant_actor(HTTPAuthorizationCredentials(scheme="Bearer",credentials=token),db)
    assert exc.value.status_code==401
