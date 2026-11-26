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
