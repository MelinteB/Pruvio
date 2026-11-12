"""Bridge contract. Invoke issuance ONLY from verified, existing Pruvs backend auth.
Do not place PRUVS_BRIDGE_SECRET in Pruvs browser/mobile code.
"""
from datetime import datetime,timezone,timedelta
import jwt
from .config import get_settings
from .models import uid

def issue_session_token(authenticated_pruvs_user_id: str):
    now=datetime.now(timezone.utc)
    return jwt.encode({'iss':'pruvs-core','aud':'pruvs-business','typ':'customer_session',
        'sub':str(authenticated_pruvs_user_id),'jti':uid(),'iat':now,'exp':now+timedelta(minutes=15)},
        get_settings().pruvs_bridge_secret,algorithm='HS256')

def issue_receipt_proof(authenticated_pruvs_user_id: str, owned_receipt_id: str,
                        verified_store_id: str, amount_minor: int, currency='RON'):
    """Caller must first verify receipt ownership + store association in trusted Pruvs DB.
    'Verified' here means server-originated/owned receipt, NOT a fiscal authenticity guarantee.
    Merchant approval is still required to award stamps.
    """
    now=datetime.now(timezone.utc)
    return jwt.encode({'iss':'pruvs-core','aud':'pruvs-business','typ':'receipt_proof',
        'sub':str(authenticated_pruvs_user_id),'receipt_id':str(owned_receipt_id),
        'store_id':str(verified_store_id),'amount_minor':amount_minor,'currency':currency,
        'jti':uid(),'iat':now,'exp':now+timedelta(minutes=5)},
        get_settings().pruvs_bridge_secret,algorithm='HS256')
