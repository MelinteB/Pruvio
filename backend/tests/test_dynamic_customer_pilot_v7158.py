"""Core v7.1.58: customer receipt access follows signed-in membership, not env user IDs.

This suite calls no Render/Business API and uses no customer credentials.
The Business-side membership and merchant approval gate has its own DB tests.
"""
import pytest
from fastapi import HTTPException

from app.react_app import loyalty_pilot_access_v7158 as access

FLAGS = (
    'PRUVS_LOYALTY_ENABLED',
    'PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED',
    'PRUVS_LOYALTY_RECEIPT_V06_ENABLED',
    'PRUVS_LOYALTY_CUSTOMER_CODES_V12_ENABLED',
)


@pytest.fixture
def enabled(monkeypatch):
    for name in FLAGS:
        monkeypatch.setenv(name, 'true')
    monkeypatch.setenv('PRUVS_LOYALTY_RECEIPT_V06_PILOT_USER_IDS', '2')


def test_authenticated_account_uses_business_membership_not_legacy_id(enabled, monkeypatch):
    seen = []
    def business(path, *, user_id):
        seen.append((path, user_id))
        return {'eligible': str(user_id) == '6',
                'reason': 'joined_approved_merchant' if str(user_id) == '6'
                           else 'no_joined_approved_merchant'}
    monkeypatch.setattr(access, 'call_business', business)

    assert access.pilot_allowed(6) is True
    assert access.pilot_allowed(2) is False   # formerly allowlisted ID
    assert seen == [
        ('/v1/customer/pilot/receipt-eligibility-v0614', 6),
        ('/v1/customer/pilot/receipt-eligibility-v0614', 2),
    ]

    s6 = access.receipt_status(6)
    s2 = access.receipt_status(2)
    assert s6['customer_codes_v12_enabled'] is True
    assert s6['receipt_v06_enabled'] is True
    assert s2['customer_codes_v12_enabled'] is False
    assert s2['receipt_access_reason'] == 'no_joined_approved_merchant'
    assert s2['claims_read_enabled'] is True


def test_business_downtime_or_malformed_response_fails_closed(enabled,monkeypatch):
    def down(*args,**kwargs):
        raise HTTPException(status_code=503,detail='Business unavailable')
    monkeypatch.setattr(access, 'call_business', down)
    access=access.pilot_access(6)
    assert access == {'eligible':False,'reason':'eligibility_unavailable'}
    with pytest.raises(HTTPException) as exc:
        access.pilot_ready(6)
    assert exc.value.status_code == 503
    assert access.receipt_status(6)[
        'customer_codes_v12_enabled'] is False

    monkeypatch.setattr(access, 'call_business', lambda *args, **kwargs:
                        {'eligible': 'true', 'reason': 'joined_approved_merchant'})
    assert access.pilot_allowed(6) is False


def test_unjoined_customer_denied_new_claim_but_can_read_history(enabled,monkeypatch):
    monkeypatch.setattr(access, 'call_business', lambda *args, **kwargs:
                        {'eligible':False,'reason':'no_joined_approved_merchant'})
    with pytest.raises(HTTPException) as exc:
        access.pilot_ready(6)
    assert exc.value.status_code == 403

    # Read-only claim history must survive a merchant's revoked approval.
    monkeypatch.setattr(access, 'call_business', lambda *args, **kwargs: [])
    assert access.pilot_ready(6, require_eligibility=False) is None


def test_legacy_id_list_cannot_grant_receipt_access(enabled, monkeypatch):
    monkeypatch.setenv('PRUVS_LOYALTY_RECEIPT_V06_PILOT_USER_IDS', '2,6,1000')
    monkeypatch.setattr(access, 'call_business',lambda *args, **kwargs: {
        'eligible': False, 'reason': 'no_joined_approved_merchant'
    })
    assert access.pilot_allowed(2) is False
    assert access.pilot_allowed(6) is False
    assert access.pilot_allowed(1000) is False
    assert access.pilot_allowed(None) is False


def test_flags_remain_enforced_even_with_approved_membership(enabled,monkeypatch):
    monkeypatch.setattr(access, 'call_business', lambda *args, **kwargs:
                        {'eligible':True,'reason':'joined_approved_merchant'})
    monkeypatch.setenv('PRUVS_LOYALTY_RECEIPT_V06_ENABLED','false')
    with pytest.raises(HTTPException) as exc:
        access.pilot_ready(6)
    assert exc.value.status_code == 503
    s=access.receipt_status(6)
    assert s['receipt_v06_enabled'] is False
    assert s['customer_codes_v12_enabled'] is False
