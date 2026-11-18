"""Manage unpublished campaigns without leaking them into public Core offers."""
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business.db import Base
from business.models import Merchant,Program,Promotion,Store
from business import pilot_v05

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def business():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        merchant=Merchant(name='Sample Restaurant',status='active')
        other=Merchant(name='Other Shop',status='active')
        db.add_all((merchant,other));db.flush()
        store=Store(merchant_id=merchant.id,name='Central',address='Bucharest',
                    latitude=44.44,longitude=26.10,active=True)
        db.add(store);db.flush()
        program=Program(merchant_id=merchant.id,store_id=store.id,
                        title='Coffee visits',description='Five verified visits',
                        stamps_required=5,min_purchase_minor=2500,reward_minor=1000,
                        currency='RON',status='published')
        db.add(program);db.commit()
        staff=SimpleNamespace(merchant_id=merchant.id,role='owner')
        yield db,program,staff,other.id
    engine.dispose()


def proposal(program):
    return pilot_v05.PromotionIn(
        program_id=program.id,headline='Coffee tastes even better',
        message='Earn your reward after five verified purchases.',
        duration_days=14,
    )


def test_draft_archive_restore_is_private_until_explicit_publish(business):
    db,program,staff,_=business
    p=pilot_v05.merchant_create_promo(proposal(program),staff=staff,db=db)
    archived=pilot_v05.archive_unpublished_promotion(p['id'],staff=staff,db=db)
    assert archived['status']=='archived'
    assert pilot_v05.public_promotions(limit=10,db=db)==[]
    returned=pilot_v05.restore_archived_promotion(p['id'],staff=staff,db=db)
    assert returned['status']=='draft'
    assert returned['published_at'] is None
    assert returned['expires_at'] is None
    assert pilot_v05.public_promotions(limit=10,db=db)==[]
    result=pilot_v05.publish_promotion(p['id'],staff=staff,db=db)
    assert result['status']=='published'
    assert len(pilot_v05.public_promotions(limit=10,db=db))==1


def test_unpublish_reopen_edit_then_republish_is_explicit(business):
    db,program,staff,_=business
    created=pilot_v05.merchant_create_promo(proposal(program),staff=staff,db=db)
    pid=created['id']
    pilot_v05.publish_promotion(pid,staff=staff,db=db)
    paused=pilot_v05.unpublish_promotion(pid,staff=staff,db=db)
    assert paused['status']=='paused'
    assert pilot_v05.public_promotions(limit=10,db=db)==[]
    with pytest.raises(HTTPException) as e:
        pilot_v05.update_promotion_draft(pid,proposal(program),staff=staff,db=db)
    assert e.value.status_code==409
    reopened=pilot_v05.reopen_unpublished_promotion(pid,staff=staff,db=db)
    assert reopened['status']=='draft'
    assert reopened['expires_at'] is None
    updated=pilot_v05.update_promotion_draft(
        pid,pilot_v05.PromotionIn(**{**proposal(program).model_dump(),
                                    'headline':'Updated coffee promotion'}),staff=staff,db=db)
    assert updated['headline']=='Updated coffee promotion'
    assert pilot_v05.public_promotions(limit=10,db=db)==[]
    pilot_v05.publish_promotion(pid,staff=staff,db=db)
    assert len(pilot_v05.public_promotions(limit=10,db=db))==1


def test_live_campaign_cannot_be_archived_without_unpublishing(business):
    db,program,staff,_=business
    created=pilot_v05.merchant_create_promo(proposal(program),staff=staff,db=db)
    pilot_v05.publish_promotion(created['id'],staff=staff,db=db)
    with pytest.raises(HTTPException) as e:
        pilot_v05.archive_unpublished_promotion(created['id'],staff=staff,db=db)
    assert e.value.status_code==409
    assert len(pilot_v05.public_promotions(limit=10,db=db))==1


def test_expired_published_campaign_can_be_archived_without_public_exposure(business):
    db,program,staff,_=business
    created=pilot_v05.merchant_create_promo(proposal(program),staff=staff,db=db)
    pilot_v05.publish_promotion(created['id'],staff=staff,db=db)
    promotion=db.get(Promotion,created['id'])
    promotion.expires_at=pilot_v05.utcnow()-timedelta(days=1)
    db.commit()
    assert pilot_v05.public_promotions(limit=10,db=db)==[]
    assert pilot_v05.archive_unpublished_promotion(created['id'],staff=staff,db=db)['status']=='archived'


def test_transitions_are_tenant_scoped_and_role_protected(business):
    db,program,staff,other_id=business
    created=pilot_v05.merchant_create_promo(proposal(program),staff=staff,db=db)
    other=SimpleNamespace(role='owner',merchant_id=other_id)
    analyst=SimpleNamespace(role='analyst',merchant_id=staff.merchant_id)
    for callback in (pilot_v05.reopen_unpublished_promotion,
                     pilot_v05.archive_unpublished_promotion,
                     pilot_v05.restore_archived_promotion):
        with pytest.raises(HTTPException) as err:
            callback(created['id'],staff=other,db=db)
        assert err.value.status_code==404
        with pytest.raises(HTTPException) as err:
            callback(created['id'],staff=analyst,db=db)
        assert err.value.status_code==403
    assert db.get(Promotion,created['id']).status=='draft'


def test_restore_requires_published_linked_program(business):
    db,program,staff,_=business
    created=pilot_v05.merchant_create_promo(proposal(program),staff=staff,db=db)
    pilot_v05.archive_unpublished_promotion(created['id'],staff=staff,db=db)
    program.status='paused'
    db.commit()
    with pytest.raises(HTTPException) as err:
        pilot_v05.restore_archived_promotion(created['id'],staff=staff,db=db)
    assert err.value.status_code==409
    assert db.get(Promotion,created['id']).status=='archived'


def test_campaign_library_supports_status_filters_preview_and_inactive_actions():
    frontend=(ROOT/'business_frontend/src/CampaignLibrary.jsx').read_text()
    studio=(ROOT/'business_frontend/src/PromotionConsole.jsx').read_text()
    entry=(ROOT/'business_frontend/src/main.jsx').read_text()
    for word in ("Unpublished","Drafts","Paused","Live","Expired","Archived","All campaigns"):
        assert word in frontend
    for action in ("Reopen draft","Restore draft","Unpublish","Publish","Archive","Preview"):
        assert action in frontend
    assert "p.status==='published'&&p.expires_at" in frontend
    assert "canManage&&p.effectiveStatus" in frontend
    assert "CorePromotionPreview" in frontend
    assert "role=\"dialog\"" in frontend
    assert "setWorkspaceView('library')" in studio
    assert "initialView=\"library\"" in entry
    assert "canManage={['owner','manager'].includes(me?.role)}" in entry


def test_core_and_business_use_different_original_logo_assets():
    core=(ROOT/'frontend/src/main.jsx').read_text()
    core_css=(ROOT/'frontend/src/core-v7160-brand.css').read_text()
    business=(ROOT/'business_frontend/src/main.jsx').read_text()
    merchant=(ROOT/'business_frontend/src/MerchantOverview.jsx').read_text()
    assert '/static/pruvs-logo.png' in core
    assert '/static/pruvs-mark-compact.webp' not in core  # no duplicated sidebar logo
    assert '#1958e6' in core_css
    assert 'business-favicon.svg' in business
    assert '/business/business-favicon.svg' in merchant
    assert "MerchantOverview" in business
    assert "core-v7160-brand.css" in core


def test_new_release_versions_are_synchronized():
    reliability=(ROOT/'app/reliability.py').read_text()
    script=(ROOT/'frontend/scripts/stamp-build.mjs').read_text()
    worker=(ROOT/'app/static/react-service-worker.js').read_text()
    business=(ROOT/'business/main.py').read_text()
    assert 'RELEASE = "7.1.61"' in reliability
    assert "version:'7.1.61'" in script
    assert 'pruvs-shell-v7.1.61' in worker
    assert "version='0.6.17'" in business
