"""Authenticated, read-only v0.6.9 receipt pilot readiness.

No migration is ever executed in an HTTP request. This diagnostic reveals
boolean readiness only, never connection strings, keys or customer data.
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .db import engine
from .models import Staff
from .schema_readiness import check_schema
from .security import merchant_actor

router = APIRouter(tags=['Receipt pilot readiness'])


def _on(name):
    return os.getenv(name, '').strip().lower() == 'true'


def summarize_readiness(checks, *, receipts_enabled, codes_enabled,
                        merchant_allowed, evidence_required):
    checks = {name: bool(checks.get(name)) for name in (
        'campaign_media', 'customer_codes', 'discount_reconciliation'
    )}
    requirements = {
        'business_receipt_pilot': bool(receipts_enabled),
        'customer_claim_codes': bool(codes_enabled),
        'merchant_allowlisted': bool(merchant_allowed),
        'consented_receipt_review_required': bool(evidence_required),
        'campaign_media_migrated': checks['campaign_media'],
        'customer_codes_migrated': checks['customer_codes'],
        'reward_reconciliation_migrated': checks['discount_reconciliation'],
    }
    blocked = [name for name, passed in requirements.items() if not passed]
    return {
        'status': 'ready' if not blocked else 'not_ready',
        'receipt_review_ready': not blocked,
        'requirements': requirements,
        'blocked_by': blocked,
        'notice': ('No database changes were made by this check. '
                   'Run and validate additive migrations only after staging backup.'),
    }


def require_reward_schema(db: Session):
    """Stop audited reward writes clearly until Business b10 is installed."""
    try:
        checks = check_schema(db.connection())
    except Exception:
        checks = {}
    if not checks.get('discount_reconciliation'):
        raise HTTPException(503,
            'Reward confirmation is unavailable: Business staging discount '
            'reconciliation migration is not ready.')


@router.get('/v1/merchant/receipt-pilot/readiness')
def merchant_receipt_readiness(staff: Staff = Depends(merchant_actor)):
    try:
        flags = check_schema(engine())
    except Exception:
        flags = {}
    merchants = {part.strip() for part in os.getenv(
        'PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS', '').split(',') if part.strip()}
    return summarize_readiness(
        flags,
        receipts_enabled=_on('PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED'),
        codes_enabled=_on('PRUVS_BUSINESS_CUSTOMER_CODES_V12_ENABLED'),
        merchant_allowed=staff.merchant_id in merchants,
        evidence_required=_on('PRUVS_BUSINESS_V06_REQUIRE_EVIDENCE'),
    )
