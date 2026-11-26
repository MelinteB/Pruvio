"""Focused checks for Release 02 readiness and campaign rules."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from business import pilot_readiness_v069 as readiness
from business import pilot_v05 as pilot
from business.campaign_skills_v0624 import CAMPAIGN_SKILLS
from business.ai_campaign_v067 import CampaignBrief

def test_readiness_requires_all_flags_and_schema():
    checks={'campaign_media':True,'customer_codes':True,'discount_reconciliation':True}
    kwargs=dict(receipts_enabled=True,codes_enabled=True,merchant_allowed=True,evidence_required=True)
    assert readiness.summarize_readiness(checks,**kwargs)['receipt_review_ready']
    for key in kwargs:
        report=readiness.summarize_readiness(checks,**{**kwargs,key:False})
        assert not report['receipt_review_ready']
        assert report['blocked_by']

def test_acquisition_gate_fails_closed(monkeypatch):
    monkeypatch.setattr(readiness,'acquisition_gate_enabled',lambda:True)
    monkeypatch.setattr(readiness,'merchant_receipt_report',lambda db,mid:{'receipt_review_ready':False})
    assert not readiness.merchant_acquisition_ready(None,'merchant')
    monkeypatch.setattr(readiness,'merchant_receipt_report',lambda db,mid:{'receipt_review_ready':True})
    assert readiness.merchant_acquisition_ready(None,'merchant')

def test_publish_requires_activation(monkeypatch):
    p=SimpleNamespace(merchant_id='m',store_id='s',status='published')
    staff=SimpleNamespace(merchant_id='m')
    merchant=SimpleNamespace(id='m',status='active')
    store=SimpleNamespace(merchant_id='m',active=True)
    db=SimpleNamespace(get=lambda cls,key:merchant if key=='m' else store)
    monkeypatch.setattr(pilot,'can_reopen_program',lambda *a:p)
    monkeypatch.setattr(readiness,'merchant_acquisition_ready',lambda *a:False)
    with pytest.raises(HTTPException) as exc:
        pilot.require_publishable_campaign(db,staff,None)
    assert exc.value.status_code==409
    monkeypatch.setattr(readiness,'merchant_acquisition_ready',lambda *a:True)
    pilot.require_publishable_campaign(db,staff,None)

def test_skills_have_bilingual_versioned_direction():
    assert len(CAMPAIGN_SKILLS)==9
    for skill in CAMPAIGN_SKILLS.values():
        assert skill['version']==1
        assert set(skill['direction'])=={'en','ro'}
        assert all(skill['direction'].values())
    assert CampaignBrief(program_id='x'*36,goal='Return for more').skill_id=='loyalty'

import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from business import main as business_main
from business.db import Base
from business.models import Merchant, Store, Staff, Program, Membership, Promotion, Reward
from business.models_v0612 import MerchantPilotEnrollment
from business import campaign_gallery_v0624 as galleries
from business import management_v0624 as management
from business.ai_campaign_v067 import campaign_provider_input

@pytest.fixture
def lifecycle_db(monkeypatch):
    url=os.getenv('PRUVS_TEST_DATABASE_URL','sqlite://')
    # Only a dedicated CI database may be used for destructive test setup.
    if url!='sqlite://' and not url.startswith('postgresql+psycopg://pruvs_test:'):
        raise RuntimeError('Refusing non-test database')
    engine=create_engine(url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine,expire_on_commit=False) as db:
            merchant=Merchant(name='Release 02 test');db.add(merchant);db.flush()
            staff=Staff(merchant_id=merchant.id,email='owner@example.test',password_hash='test',role='owner')
            store=Store(merchant_id=merchant.id,name='Test cafe',latitude=44.4,longitude=26.1)
            db.add_all([staff,store]);db.flush()
            program=Program(merchant_id=merchant.id,store_id=store.id,title='Visit rewards',stamps_required=5,reward_minor=2000,status='published')
            db.add(program);db.commit()
            yield db,merchant,staff,store,program
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()

def test_actual_discovery_and_join_require_all_activation_controls(lifecycle_db,monkeypatch):
    db,m,staff,store,p=lifecycle_db
    for flag in ('PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED','PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED','PRUVS_BUSINESS_CUSTOMER_CODES_V12_ENABLED','PRUVS_BUSINESS_V06_REQUIRE_EVIDENCE'):
        monkeypatch.setenv(flag,'true')
    assert business_main.discover(latitude=None,longitude=None,radius_km=10,db=db)==[]
    with pytest.raises(HTTPException):
        business_main.join_program(p.id,consumer_id='customer-a',db=db)
    enrollment=MerchantPilotEnrollment(merchant_id=m.id,status='approved')
    db.add(enrollment);db.commit()
    assert readiness.merchant_receipt_report(db,m.id)['receipt_review_ready']
    assert business_main.discover(latitude=None,longitude=None,radius_km=10,db=db)[0]['program']['id']==p.id
    result=business_main.join_program(p.id,consumer_id='customer-a',db=db)
    assert result['membership_id']
    enrollment.status='revoked';db.commit()
    assert business_main.discover(latitude=None,longitude=None,radius_km=10,db=db)==[]
    assert db.scalar(select(Membership).where(Membership.program_id==p.id))

def test_archive_protects_existing_customer_progress(lifecycle_db):
    db,m,staff,store,p=lifecycle_db
    p.status='paused';db.add(Membership(program_id=p.id,consumer_id='customer-a',stamps=1));db.commit()
    with pytest.raises(HTTPException) as e:
        business_main.archive_location(store.id,staff=staff,db=db)
    assert e.value.status_code==409
    assert store.active
    assert db.scalar(select(Membership).where(Membership.program_id==p.id)).stamps==1

def test_duplicate_program_is_idempotent_and_audited(lifecycle_db):
    db,m,staff,store,p=lifecycle_db
    first=business_main.duplicate_program(p.id,staff=staff,db=db)
    second=business_main.duplicate_program(p.id,staff=staff,db=db)
    assert first['id']==second['id'] and first['status']=='draft'
    assert db.scalar(select(management.ManagementAudit).where(management.ManagementAudit.object_id==first['id'])).action=='duplicate'

def test_gallery_roundtrip_order_and_cross_tenant_rejection(lifecycle_db,monkeypatch):
    db,m,staff,store,p=lifecycle_db
    promo=Promotion(merchant_id=m.id,program_id=p.id,headline='Coffee reward',message='Enjoy another visit.')
    db.add(promo);db.flush()
    keys=['campaigns/'+m.id+'/'+('a'*32)+'.jpg','campaigns/'+m.id+'/'+('b'*32)+'.jpg']
    monkeypatch.setattr(galleries,'bucket_config',lambda:{'PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL':'https://media.example.test'})
    def read(staff,key):
        if not key.startswith('campaigns/'+staff.merchant_id+'/'):
            raise HTTPException(403,'Other merchant')
        return b'normalized-photo'
    monkeypatch.setattr(galleries,'read_merchant_campaign_source',read)
    assets=galleries.validate_gallery(db,staff,keys,'Coffee')
    galleries.save_gallery(db,promo,assets);db.commit()
    assert [x['media_key'] for x in galleries.gallery_assets(db,promo)]==keys
    galleries.save_gallery(db,promo,list(reversed(assets)));db.commit()
    assert [x['media_key'] for x in galleries.gallery_assets(db,promo)]==list(reversed(keys))
    with pytest.raises(HTTPException):
        galleries.validate_gallery(db,staff,['campaigns/other/'+'c'*32+'.jpg'],'Coffee')
    with pytest.raises(HTTPException):
        galleries.validate_gallery(db,staff,[keys[0],keys[0]],'Coffee')

def test_multi_photo_ai_context_keeps_all_images():
    result=campaign_provider_input({'program':'test'},[b'photo-one',b'photo-two'])
    assert len(result[0]['content'])==3
    assert all(row['type']=='input_image' for row in result[0]['content'][1:])
