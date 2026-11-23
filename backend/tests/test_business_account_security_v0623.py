"""Regression coverage for Business account password policy and tenant isolation.

Run from backend: pytest -q tests/test_business_account_security_v0623.py
"""
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from business.db import Base
from business.merchant_enrollment import SignupData
from business.models import Merchant, Staff
from business.password_recovery import RecoveryConfirm, PasswordChange, _token, _reset_url
from business.security import hasher, password_version
from business.staff_management import StaffUpdate, update_staff, MerchantStaffAudit


def test_policy_in_enrollment_and_recovery():
    for model, field in ((SignupData, "password"), (RecoveryConfirm, "new_password"),
                         (PasswordChange, "new_password")):
        metadata = model.model_fields[field].metadata
        assert any(getattr(x, "min_length", None) == 15 for x in metadata)
        assert any(getattr(x, "max_length", None) == 128 for x in metadata)


def test_password_bound_reset_is_not_reusable(monkeypatch):
    staff = Staff(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", merchant_id="m1",
                  email="merchant@example.test", password_hash=hasher.hash("initial secure password"),
                  role="owner", active=True)
    monkeypatch.setattr("business.password_recovery.get_settings",
                        lambda: SimpleNamespace(business_jwt_secret="test-secret-32-characters-long-12345"))
    token = _token(staff)
    payload = jwt.decode(token, "test-secret-32-characters-long-12345", algorithms=["HS256"],
                         issuer="pruvs-business", audience="pruvs-business-password-reset")
    assert payload["pv"] == password_version(staff.password_hash)
    staff.password_hash = hasher.hash("completely different password")
    assert payload["pv"] != password_version(staff.password_hash)


def test_reset_link_requires_https_origin(monkeypatch):
    monkeypatch.setenv("PRUVS_BUSINESS_PUBLIC_ORIGIN", "http://example.test")
    with pytest.raises(HTTPException) as error:
        _reset_url("dummy")
    assert error.value.status_code == 503
    monkeypatch.setenv("PRUVS_BUSINESS_PUBLIC_ORIGIN", "https://pruvs.io")
    assert _reset_url("token") == "https://pruvs.io/business/merchant-reset.html#token=token"


def _setup():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def test_cross_merchant_updates_denied():
    db = _setup()
    try:
        a = Merchant(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", name="A", status="active")
        b = Merchant(id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", name="B", status="active")
        db.add_all([a,b])
        owner = Staff(id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                      merchant_id=a.id, email="owner@example.test",
                      password_hash="hash", role="owner",active=True)
        foreign = Staff(id="dddddddd-dddd-dddd-dddd-dddddddddddd",
                        merchant_id=b.id, email="foreign@example.test",
                        password_hash="hash", role="staff",active=True)
        db.add_all([owner,foreign]);db.commit()
        with pytest.raises(HTTPException) as error:
            update_staff(foreign.id, StaffUpdate(confirm=foreign.id,active=False),
                         actor=owner, db=db)
        assert error.value.status_code == 404
        assert db.get(Staff,foreign.id).active
    finally:
        db.close()


def test_cannot_disable_sole_merchant_owner():
    db = _setup()
    try:
        merchant = Merchant(id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", name="A", status="active")
        owner = Staff(id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                      merchant_id=merchant.id, email="owner@example.test",
                      password_hash="hash", role="owner",active=True)
        db.add_all([merchant,owner]);db.commit()
        with pytest.raises(HTTPException) as error:
            update_staff(owner.id, StaffUpdate(confirm=owner.id,active=False),
                         actor=owner, db=db)
        assert error.value.status_code == 409
        assert db.get(Staff,owner.id).active
    finally:
        db.close()
