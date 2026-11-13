"""v0.6.12: database-managed merchant pilot enrollment and Core-facing access.

Runs with an isolated in-memory SQLite database; no Render, paid AI,
production users, or real customer receipts are used.
"""
from types import SimpleNamespace
import os

# Isolated test defaults only, before Business Settings is imported.
os.environ.setdefault('BUSINESS_JWT_SECRET','test-jwt-secret-'*4)
os.environ.setdefault('PRUVS_BRIDGE_SECRET','test-bridge-secret-'*4)
os.environ.setdefault('APP_ENV','testing')

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from business.db import Base
from business.models import Merchant, Program, Staff, Store
from business.models_v0612 import MerchantPilotEnrollment, MerchantPilotAudit
from business import pilot_enrollment_v0612 as pilot
from business import pilot_v12
from business import main as business_main


@pytest.fixture
def data(monkeypatch):
    monkeypatch.setenv('PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED','true')
    monkeypatch.setenv('PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS','not-an-active-id')
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        m1=Merchant(name='Merchant One',status='active')
        m2=Merchant(name='Merchant Two',status='active')
        db.add_all([m1,m2]);db.flush()
        owner=Staff(merchant_id=m1.id,email='owner@example.test',
            password_hash='test-only',role='owner',active=True)
        other=Staff(merchant_id=m2.id,email='other@example.test',
            password_hash='test-only',role='owner',active=True)
        admin=Staff(merchant_id=m2.id,email='admin@example.test',
            password_hash='test-only',role='platform_admin',active=True)
        store1=Store(merchant_id=m1.id,name='One Downtown',address='Bucharest',
                     latitude=44.4,longitude=26.1,active=True)
        store2=Store(merchant_id=m2.id,name='Two Downtown',address='Bucharest',
                     latitude=44.5,longitude=26.2,active=True)
        db.add_all([owner,other,admin,store1,store2]);db.flush()
        program=Program(merchant_id=m1.id,store_id=store1.id,title='Visit rewards',
            description='Five verified purchases',stamps_required=5,
            min_purchase_minor=1000,reward_minor=500,currency='RON',status='published')
        db.add(program);db.commit()
        yield db,m1,m2,owner,other,admin,program


def test_new_merchant_not_automatically_allowed(data):
    db,m1,m2,owner,other,admin,program=data
    assert not pilot.merchant_pilot_allowed(db,m1.id)
    assert not pilot_v12.merchant_pilot_allowed(db,m1.id)
    current=pilot.my_pilot_access(staff=owner,db=db)
    assert current['status']=='not_requested'
    assert current['request_supported'] is True
    assert current['has_published_program'] is True
    offers=business_main.discover(latitude=None,longitude=None,radius_km=10,db=db)
    row=next(row for row in offers if row['program']['id']==program.id)
    assert row['receipt_pilot_allowed'] is False
    assert row['merchant_id']==m1.id


def test_owner_request_admin_approval_revoke_and_audit(data):
    db,m1,m2,owner,other,admin,program=data
    state=pilot.request_pilot_access(staff=owner,db=db)
    assert state['status']=='requested'
    assert pilot.request_pilot_access(staff=owner,db=db)['status']=='requested'
    assert not pilot.merchant_pilot_allowed(db,m1.id)
    with pytest.raises(HTTPException) as rejected:
        pilot.require_platform_admin(owner)
    assert rejected.value.status_code==403
    with pytest.raises(HTTPException) as rejected:
        pilot.platform_decide_pilot(m1.id,pilot.PilotDecisionIn(action='approve'),
                                   staff=owner,db=db)
    assert rejected.value.status_code==403  # Normally enforced by FastAPI dependency.
    allowed=pilot.platform_decide_pilot(
        m1.id,pilot.PilotDecisionIn(action='approve'),staff=admin,db=db)
    assert allowed['status']=='approved'
    assert pilot.merchant_pilot_allowed(db,m1.id)
    assert not pilot.merchant_pilot_allowed(db,m2.id)
    offers=business_main.discover(latitude=None,longitude=None,radius_km=10,db=db)
    assert next(row for row in offers if row['program']['id']==program.id)['receipt_pilot_allowed'] is True
    admin_rows=pilot.platform_pilot_enrollments(staff=admin,db=db)
    assert len(admin_rows)==1
    assert admin_rows[0]['merchant_name']=='Merchant One'
    with pytest.raises(HTTPException) as duplicate:
        pilot.platform_decide_pilot(m1.id,pilot.PilotDecisionIn(action='approve'),
                                   staff=admin,db=db)
    assert duplicate.value.status_code==409
    revoked=pilot.platform_decide_pilot(
        m1.id,pilot.PilotDecisionIn(action='revoke',note='Pilot finished'),
        staff=admin,db=db)
    assert revoked['status']=='revoked'
    assert not pilot.merchant_pilot_allowed(db,m1.id)
    audit=db.scalars(select(MerchantPilotAudit).where(
        MerchantPilotAudit.merchant_id==m1.id).order_by(MerchantPilotAudit.created_at)).all()
    assert [entry.action for entry in audit]==['request','approve','revoke']
    assert db.scalar(select(func.count(MerchantPilotAudit.id)))==3
    assert db.get(MerchantPilotEnrollment,m1.id).reviewed_by_staff_id==admin.id


def test_non_owner_cannot_request_and_unrequested_cannot_be_approved(data):
    db,m1,m2,owner,other,admin,program=data
    with pytest.raises(HTTPException) as missing:
        pilot.platform_decide_pilot(m1.id,pilot.PilotDecisionIn(action='approve'),
                                    staff=admin,db=db)
    assert missing.value.status_code==404
    analyst=SimpleNamespace(merchant_id=m1.id,id='readonly',role='analyst')
    with pytest.raises(HTTPException) as denied:
        pilot.request_pilot_access(staff=analyst,db=db)
    assert denied.value.status_code==403
    with pytest.raises(HTTPException) as ineligible:
        pilot.request_pilot_access(staff=other,db=db)
    assert ineligible.value.status_code==409


def test_denial_requires_reason_and_can_be_resubmitted(data):
    db,m1,m2,owner,other,admin,program=data
    pilot.request_pilot_access(staff=owner,db=db)
    with pytest.raises(HTTPException) as invalid:
        pilot.platform_decide_pilot(m1.id,pilot.PilotDecisionIn(action='deny'),staff=admin,db=db)
    assert invalid.value.status_code==422
    assert pilot.platform_decide_pilot(
        m1.id,pilot.PilotDecisionIn(action='deny',note='Need merchant evidence'),
        staff=admin,db=db)['status']=='denied'
    assert not pilot.merchant_pilot_allowed(db,m1.id)
    assert pilot.request_pilot_access(staff=owner,db=db)['status']=='requested'
    assert pilot.platform_decide_pilot(
        m1.id,pilot.PilotDecisionIn(action='approve'),staff=admin,db=db)['status']=='approved'


def test_disable_active_merchant_stops_claiming_even_if_approved(data):
    db,m1,m2,owner,other,admin,program=data
    pilot.request_pilot_access(staff=owner,db=db)
    pilot.platform_decide_pilot(
        m1.id,pilot.PilotDecisionIn(action='approve'),staff=admin,db=db)
    m1.status='inactive';db.commit()
    assert not pilot.merchant_pilot_allowed(db,m1.id)


def test_feature_flag_rollback_uses_legacy_allowlist_without_writing(data,monkeypatch):
    db,m1,m2,owner,other,admin,program=data
    monkeypatch.setenv('PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED','false')
    monkeypatch.setenv('PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS',m1.id)
    assert pilot.merchant_pilot_allowed(db,m1.id)
    with pytest.raises(HTTPException) as unavailable:
        pilot.request_pilot_access(staff=owner,db=db)
    assert unavailable.value.status_code==503
    assert db.get(MerchantPilotEnrollment,m1.id) is None


def test_enabled_without_b11_tables_fails_closed(monkeypatch):
    monkeypatch.setenv('PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED','true')
    monkeypatch.setenv('PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS','legacy-merchant')
    engine=create_engine('sqlite://')
    with Session(engine) as db:
        assert not pilot.merchant_pilot_allowed(db,'legacy-merchant')
        with pytest.raises(HTTPException) as error:
            pilot.require_db_mode(db)
        assert error.value.status_code==503
