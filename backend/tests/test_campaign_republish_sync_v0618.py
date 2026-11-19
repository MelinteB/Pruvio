"""Republish / customer-discovery synchronization regression suite."""
from datetime import timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from business.db import Base
from business.models import Merchant,Store,Program,Promotion
from business import pilot_v05

@pytest.fixture
def data():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        merchant=Merchant(name='Cafe',status='active')
        db.add(merchant);db.flush()
        store=Store(merchant_id=merchant.id,name='Cafe',address='Bucharest',latitude=44.4,longitude=26.1,active=True)
        db.add(store);db.flush()
        program=Program(merchant_id=merchant.id,store_id=store.id,
            title='Coffee loyalty',description='Test',stamps_required=3,
            min_purchase_minor=100,reward_minor=500,currency='RON',status='published')
        db.add(program);db.commit()
        yield db,SimpleNamespace(merchant_id=merchant.id,role='owner'),merchant,store,program
    engine.dispose()

def publish(db,staff,program):
    p=pilot_v05.merchant_create_promo(pilot_v05.PromotionIn(
       program_id=program.id,headline='Coffee loyalty offer',
       message='Get a reward after three qualifying visits.',
       duration_days=14),staff=staff,db=db)
    pilot_v05.publish_promotion(p['id'],staff=staff,db=db)
    return p['id']

def ids(db):
    return [p['id'] for p in pilot_v05.public_promotions(limit=30,db=db)]

def test_paused_campaign_is_removed_and_can_be_republished_without_copy(data):
    db,staff,merchant,store,program=data
    pid=publish(db,staff,program)
    assert pid in ids(db)
    pilot_v05.unpublish_promotion(pid,staff=staff,db=db)
    assert pid not in ids(db)
    before=db.get(Promotion,pid).published_at
    result=pilot_v05.republish_promotion(pid,staff=staff,db=db)
    assert result['status']=='published'
    assert result['expires_at'] is not None
    assert pid in ids(db)
    with pytest.raises(HTTPException) as e:
        pilot_v05.republish_promotion(pid,staff=staff,db=db)
    assert e.value.status_code==409

def test_expired_campaign_can_be_republished_with_new_period(data):
    db,staff,merchant,store,program=data
    pid=publish(db,staff,program)
    p=db.get(Promotion,pid)
    p.expires_at=pilot_v05.utcnow()-timedelta(days=1)
    db.commit()
    assert pid not in ids(db)
    res=pilot_v05.republish_promotion(pid,staff=staff,db=db)
    assert res['status']=='published'
    assert pid in ids(db)

def test_inactive_store_merchant_and_program_not_discoverable(data):
    db,staff,merchant,store,program=data
    pid=publish(db,staff,program)
    for target,column,val in ((store,'active',False),(merchant,'status','paused'),
                              (program,'status','paused')):
        old=getattr(target,column)
        setattr(target,column,val);db.commit()
        assert pid not in ids(db)
        setattr(target,column,old);db.commit()
        assert pid in ids(db)

def test_republish_is_role_tenant_and_program_protected(data):
    db,staff,merchant,store,program=data
    pid=publish(db,staff,program)
    pilot_v05.unpublish_promotion(pid,staff=staff,db=db)
    for caller,expected in ((SimpleNamespace(merchant_id='different',role='owner'),404),
                            (SimpleNamespace(merchant_id=merchant.id,role='analyst'),403)):
        with pytest.raises(HTTPException) as e:
            pilot_v05.republish_promotion(pid,staff=caller,db=db)
        assert e.value.status_code==expected
    program.status='paused';db.commit()
    with pytest.raises(HTTPException) as e:
        pilot_v05.republish_promotion(pid,staff=staff,db=db)
    assert e.value.status_code==409

def test_public_limit_not_consumed_by_large_expired_backlog(data):
    db,staff,merchant,store,program=data
    live=publish(db,staff,program)
    p=db.get(Promotion,live)
    p.published_at=pilot_v05.utcnow()-timedelta(days=3)
    for i in range(210):
        db.add(Promotion(merchant_id=merchant.id,program_id=program.id,
           headline='Expired old '+str(i),message='Past campaign no longer available.',
           status='published',duration_days=1,
           published_at=pilot_v05.utcnow()-timedelta(hours=i/10),
           expires_at=pilot_v05.utcnow()-timedelta(minutes=1)))
    db.commit()
    assert ids(db)==[live]

def test_business_ux_exposes_republish_to_merchant():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    library=(root/'business_frontend/src/CampaignLibrary.jsx').read_text()
    editor=(root/'business_frontend/src/PromotionConsole.jsx').read_text()
    assert "onRepublish={canManage?republishCampaign:undefined}" in editor
    assert "manage('republish'" in editor
    assert library.count('onRepublish?.(p)')==2
