"""Live customer eligibility for Pruvs receipt rewards (Core v7.1.58).

Only a signed-in Core account's server-derived identity is passed to Business.
In dynamic mode, Business checks that it has a membership at a published,
active and platform-approved merchant. Numeric user IDs never grant permission.
"""
import os
from fastapi import HTTPException
from app.react_app.loyalty_gateway import call_business, enabled


def pilot_access(user_id):
    if user_id is None or not str(user_id).strip():
        return {'eligible': False, 'reason': 'unauthenticated'}

    mode=os.getenv('PRUVS_LOYALTY_CUSTOMER_ELIGIBILITY_MODE','legacy_ids').strip().lower()
    if mode=='merchant_membership':
        try:
            result=call_business('/v1/customer/pilot/receipt-eligibility-v0614',user_id=user_id)
        except HTTPException:
            return {'eligible': False, 'reason': 'eligibility_unavailable'}
        if not isinstance(result,dict) or type(result.get('eligible')) is not bool:
            return {'eligible': False, 'reason': 'eligibility_unavailable'}
        return {
            'eligible': result['eligible'] is True,
            'reason': result.get('reason','eligibility_unavailable'),
        }

    if mode=='legacy_ids':
        # Backwards-compatible rollback only. Dynamic mode ignores this list.
        allowed={part.strip() for part in os.getenv(
            'PRUVS_LOYALTY_RECEIPT_V06_PILOT_USER_IDS',''
        ).split(',') if part.strip()}
        granted=str(user_id) in allowed
        return {'eligible': granted, 'reason': 'legacy_invited' if granted else 'legacy_not_invited'}

    # An unexpected configuration must not grant access.
    return {'eligible': False, 'reason': 'eligibility_mode_unavailable'}


def pilot_allowed(user_id):
    return pilot_access(user_id)['eligible']


def flags():
    loyalty_on=enabled()
    receipts_on=(loyalty_on and
        os.getenv('PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED','false').lower()=='true')
    v06_on=receipts_on and os.getenv('PRUVS_LOYALTY_RECEIPT_V06_ENABLED','false').lower()=='true'
    codes_on=v06_on and os.getenv('PRUVS_LOYALTY_CUSTOMER_CODES_V12_ENABLED','false').lower()=='true'
    return loyalty_on, receipts_on, v06_on, codes_on


def pilot_ready(user_id, *, require_eligibility=True):
    _,_,v06_on,_=flags()
    if not v06_on:
        raise HTTPException(503,'Verified receipt submissions are not enabled in this environment')
    if require_eligibility:
        access=pilot_access(user_id)
        if not access['eligible']:
            if access['reason']=='eligibility_unavailable':
                raise HTTPException(503,'Customer receipt eligibility is temporarily unavailable')
            raise HTTPException(403,'Join an approved merchant loyalty program to verify receipts')


def receipt_status(user_id):
    # No heavy OCR imports on the highly-frequent Rewards status endpoint.
    loyalty_on,receipts_on,v06_on,codes_on=flags()
    access=pilot_access(user_id) if v06_on else {
        'eligible':False,'reason':'receipt_pilot_disabled'}
    return {
        'enabled': loyalty_on,
        'receipt_claims_enabled': receipts_on,
        'claims_read_enabled': v06_on,
        'receipt_v06_enabled': bool(v06_on and access['eligible']),
        'customer_codes_v12_enabled': bool(codes_on and access['eligible']),
        'receipt_access_reason': access['reason'],
        'message': 'Receipt earning requires an approved merchant program and verified purchase.',
    }
