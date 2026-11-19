"""End-to-end database lifecycle tests: Business state is Core feed authority."""
from datetime import timedelta
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business.db import Base
from business.models import Merchant,Program,Store,Promotion
from business import pilot_v05

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('PRUVS_BUSINESS_PLACES_ENABLED','false')
    dbengine=create_engine('sqlite://')
    Base.metadata.create_all(dbengine)
    with Session(dbengine) as db:
        merchant=Merchant(name='Bistro Central',status='active')
        other=Merchant(name='Foreign Restaurant',status='active')
        db.add_all((merchant,other));db.flush()
        store=Store(merchant_id=merchant.id,name='Downtown',address='Bucharest',
                    latitude=44.43,longitude=26.11,active=True)
        db.add(store);db.flush()
        program=Program(merchant_id=merchant.id,store_id=store.id,
                        title='Three verified lunches',description='Three visits',
                        stamps_required=3,min_purchase_minor=1000,
                        reward_minor=2000,currency='RON',status='published')
        db.add(program);db.commit()
        staff=SimpleNamespace(merchant_id=merchant.id,role='owner')
        yield db,merchant,other,store,program,staff
    dbengine.dispose()

def draft(db,program,staff):
    body=pilot_v05.PromotionIn(
        program_id=program.id,headline='Lunch loyalty bonus',
        message='Three approved visits unlock a reward.',
        duration_days=14)
    return pilot_v05.merchant_create_promo(body,staff=staff,db=db)

def test_paused_campaign_republishes_without_creating_a_new_record(setup):
    db,merchant,other,store,program,staff=setup
    created=draft(db,program,staff)
    first=pilot_v05.publish_promotion(created['id'],staff=staff,db=db)
    assert first['is_public'] is True
    assert len(pilot_v05.public_promotions(limit=30,db=db))==1
    stopped=pilot_v05.unpublish_promotion(created['id'],staff=staff,db=db)
    assert stopped['is_public'] is False
    assert pilot_v05.public_promotions(limit=30,db=db)==[]
    republished=pilot_v05.republish_promotion(created['id'],staff=staff,db=db)
    assert republished['id']==created['id']
    assert republished['effective_status']=='published'
    assert republished['is_public'] is True
    assert republished['expires_at']!=created['expires_at']
    assert len(pilot_v05.public_promotions(limit=30,db=db))==1
    assert db.query(Promotion).count()==1
    with pytest.raises(HTTPException) as exc:
        pilot_v05.republish_promotion(created['id'],staff=staff,db=db)
    assert exc.value.status_code==409

def test_expired_campaign_can_republish_but_not_leak_beforehand(setup):
    db,merchant,other,store,program,staff=setup
    created=draft(db,program,staff)
    pilot_v05.publish_promotion(created['id'],staff=staff,db=db)
    p=db.get(Promotion,created['id'])
    p.expires_at=pilot_v05.utcnow()-timedelta(minutes=5)
    db.commit()
    assert pilot_v05.public_promotions(limit=5,db=db)==[]
    assert pilot_v05.promo_json(p,db)['effective_status']=='expired'
    result=pilot_v05.republish_promotion(p.id,staff=staff,db=db)
    assert result['status']=='published' and result['is_public']
    assert len(pilot_v05.public_promotions(limit=5,db=db))==1

def test_republish_fails_when_program_paused_or_store_inactive(setup):
    db,merchant,other,store,program,staff=setup
    p=draft(db,program,staff)
    pilot_v05.publish_promotion(p['id'],staff=staff,db=db)
    pilot_v05.unpublish_promotion(p['id'],staff=staff,db=db)
    program.status='paused';db.commit()
    with pytest.raises(HTTPException) as exc:
        pilot_v05.republish_promotion(p['id'],staff=staff,db=db)
    assert exc.value.status_code==409
    program.status='published';store.active=False;db.commit()
    result=pilot_v05.republish_promotion(p['id'],staff=staff,db=db)
    assert result['is_public'] is False
    assert pilot_v05.public_promotions(limit=5,db=db)==[]
    store.active=True;db.commit()
    assert len(pilot_v05.public_promotions(limit=5,db=db))==1

def test_tenant_and_role_boundaries_for_republish(setup):
    db,merchant,other,store,program,staff=setup
    p=draft(db,program,staff)
    pilot_v05.publish_promotion(p['id'],staff=staff,db=db)
    pilot_v05.unpublish_promotion(p['id'],staff=staff,db=db)
    foreign=SimpleNamespace(merchant_id=other.id,role='owner')
    analyst=SimpleNamespace(merchant_id=merchant.id,role='analyst')
    with pytest.raises(HTTPException) as exc:
        pilot_v05.republish_promotion(p['id'],staff=foreign,db=db)
    assert exc.value.status_code==404
    with pytest.raises(HTTPException) as exc:
        pilot_v05.republish_promotion(p['id'],staff=analyst,db=db)
    assert exc.value.status_code==403
    assert pilot_v05.public_promotions(limit=5,db=db)==[]

def test_public_feed_filters_expired_records_before_limit(setup):
    db,merchant,other,store,program,staff=setup
    recent=pilot_v05.utcnow()
    valid=draft(db,program,staff)
    pilot_v05.publish_promotion(valid['id'],staff=staff,db=db)
    expired=[]
    for index in range(220):
        row=Promotion(merchant_id=merchant.id,program_id=program.id,
            headline='Expired offer '+str(index),message='Expired marketing example.',
            duration_days=14,status='published',
            published_at=recent+timedelta(seconds=index+10),
            expires_at=recent-timedelta(hours=1))
        expired.append(row)
    db.add_all(expired);db.commit()
    rows=pilot_v05.public_promotions(limit=5,db=db)
    assert len(rows)==1 and rows[0]['id']==valid['id']

def test_frontend_shows_authoritative_status_and_refreshes_when_visible():
    library=(ROOT/'business_frontend/src/CampaignLibrary.jsx').read_text()
    studio=(ROOT/'business_frontend/src/PromotionConsole.jsx').read_text()
    core=(ROOT/'frontend/src/PromotionsPreview.jsx').read_text()
    rewards=(ROOT/'frontend/src/Rewards.jsx').read_text()
    assert "if(p.effective_status)return p.effective_status" in library
    assert "onRepublish?.(p)" in library
    assert "manage('republish'" in studio
    assert "visibilitychange" in core and "focus" in core and "30000" in core
    assert "visibilitychange" in rewards and "45000" in rewards
    assert "cache:'no-store'" in (ROOT/'business_frontend/src/main.jsx').read_text()
