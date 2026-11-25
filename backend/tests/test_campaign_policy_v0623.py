from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from business import campaign_policy_v0623 as policy

def test_gate_requires_activation_and_live_campaign(monkeypatch):
    p=SimpleNamespace(id='program',merchant_id='merchant')
    db=SimpleNamespace(scalar=lambda q:None)
    monkeypatch.setattr(policy,'merchant_receipts_ready',lambda *a:False)
    with pytest.raises(HTTPException) as e:policy.enforce_campaign_gate(db,p)
    assert e.value.status_code==409
    monkeypatch.setattr(policy,'merchant_receipts_ready',lambda *a:True)
    with pytest.raises(HTTPException) as e:policy.enforce_campaign_gate(db,p)
    assert e.value.status_code==404
    db.scalar=lambda q:'active-campaign'
    policy.enforce_campaign_gate(db,p)
