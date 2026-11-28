"""Program approval must bind to the exact loyalty program and current location."""
import os

os.environ.setdefault('BUSINESS_JWT_SECRET','test-jwt-secret-'*4)
os.environ.setdefault('PRUVS_BRIDGE_SECRET','test-bridge-secret-'*4)
os.environ.setdefault('APP_ENV','testing')

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session

from business.db import Base
from business.models import Merchant,Program,Staff,Store
from business.models_v0726 import ProgramPilotAudit
from business import pilot_enrollment_v0612 as pilot


@pytest.fixture
def scope(monkeypatch):
    monkeypatch.setenv('PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED','true')
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        merchant=Merchant(name='Scope Bistro',status='active')
        other_merchant=Merchant(name='Other Bistro',status='active')
        db.add_all([merchant,other_merchant]);db.flush()
        store_a=Store(merchant_id=merchant.id,name='Central',address='Bucharest',latitude=44.4,longitude=26.1,active=True)
        store_b=Store(merchant_id=merchant.id,name='North',address='Bucharest',latitude=44.5,longitude=26.2,active=True)
        owner=Staff(merchant_id=merchant.id,email='owner@scope.test',password_hash='test',role='owner',active=True)
        admin=Staff(merchant_id=other_merchant.id,email='admin@scope.test',password_hash='test',role='platform_admin',active=True)
        db.add_all([store_a,store_b,owner,admin]);db.flush()
        first=Program(merchant_id=merchant.id,store_id=store_a.id,title='Lunch',description='lunch',stamps_required=3,min_purchase_minor=1000,reward_minor=500,currency='RON',status='published')
        second=Program(merchant_id=merchant.id,store_id=store_b.id,title='Dinner',description='dinner',stamps_required=4,min_purchase_minor=1500,reward_minor=700,currency='RON',status='published')
        db.add_all([first,second]);db.commit()
        yield db,merchant,store_a,store_b,owner,admin,first,second


def test_approval_applies_only_to_the_requested_program_and_location(scope):
    db,merchant,store_a,store_b,owner,admin,first,second=scope
    requested=pilot.request_program_pilot_access(first.id,staff=owner,db=db)
    assert requested['program_id']==first.id
    assert requested['store_id']==store_a.id
    assert requested['status']=='requested'
    approved=pilot.platform_decide_program_pilot(first.id,pilot.PilotDecisionIn(action='approve'),staff=admin,db=db)
    assert approved['allowed'] is True
    assert pilot.program_pilot_allowed(db,first) is True
    assert pilot.program_pilot_allowed(db,second) is False

    # Changes to the linked store invalidate the old approval immediately.
    first.store_id=store_b.id
    db.commit()
    assert pilot.program_pilot_allowed(db,first) is False
    refreshed=pilot.request_program_pilot_access(first.id,staff=owner,db=db)
    assert refreshed['status']=='requested'
    assert refreshed['store_id']==store_b.id
    assert pilot.program_pilot_allowed(db,first) is False
    assert [event.action for event in db.scalars(select(ProgramPilotAudit).where(
        ProgramPilotAudit.program_id==first.id).order_by(ProgramPilotAudit.created_at)).all()]==['request','approve','request']


@pytest.mark.parametrize('inactive',('store','merchant','program'))
def test_platform_cannot_approve_inactive_or_unpublished_scope(scope,inactive):
    db,merchant,store_a,store_b,owner,admin,first,second=scope
    pilot.request_program_pilot_access(first.id,staff=owner,db=db)
    if inactive=='store':store_a.active=False
    elif inactive=='merchant':merchant.status='inactive'
    else:first.status='draft'
    db.commit()
    with pytest.raises(HTTPException) as error:
        pilot.platform_decide_program_pilot(first.id,pilot.PilotDecisionIn(action='approve'),staff=admin,db=db)
    assert error.value.status_code==409


def test_unrequested_program_cannot_be_approved(scope):
    db,merchant,store_a,store_b,owner,admin,first,second=scope
    with pytest.raises(HTTPException) as error:
        pilot.platform_decide_program_pilot(first.id,pilot.PilotDecisionIn(action='approve'),staff=admin,db=db)
    assert error.value.status_code==404
