"""Opt-in coordinated campaign discovery gate. Never bypass merchant approval."""
import os
from fastapi import HTTPException
from sqlalchemy import select,or_
from .models import Promotion,utcnow
from .pilot_enrollment_v0612 import merchant_pilot_allowed

def campaign_gate_enabled():
    return os.getenv('PRUVS_CAMPAIGN_DISCOVERY_REQUIRED','false').strip().lower()=='true'

def merchant_receipts_ready(db,merchant_id):
    from .schema_readiness import check_schema
    if not all(os.getenv(name,'').strip().lower()=='true' for name in (
        'PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED','PRUVS_BUSINESS_CUSTOMER_CODES_V12_ENABLED','PRUVS_BUSINESS_V06_REQUIRE_EVIDENCE')):
        return False
    try:
        schema=check_schema(db.get_bind())
        return all(schema.get(k) for k in ('campaign_media','customer_codes','discount_reconciliation')) and merchant_pilot_allowed(db,merchant_id)
    except Exception:return False

def enforce_campaign_gate(db,program):
    if not merchant_receipts_ready(db,program.merchant_id):
        raise HTTPException(409,'Merchant receipt verification is not active.')
    now=utcnow()
    if not db.scalar(select(Promotion.id).where(Promotion.program_id==program.id,
        Promotion.merchant_id==program.merchant_id,Promotion.status=='published',
        Promotion.expires_at>now,or_(Promotion.published_at.is_(None),Promotion.published_at<=now)).limit(1)):
        raise HTTPException(404,'No active published campaign for this program.')
