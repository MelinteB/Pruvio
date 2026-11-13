"""Pruvs Business v0.6: consented receipt snapshot + scoped audited merchant review.

The merchant cannot browse customer receipts or retrieve cloud originals. One JPEG
snapshot accompanies only a specifically claimed receipt, with consent and signed
Core proof; the original remains in the customer's Pruvs account.
"""
import base64
import binascii
import hashlib
import os
import re
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import Program, Membership, PurchaseCode, ReceiptClaim, Store, Staff, utcnow
from .models_v06 import ReceiptEvidence, ReceiptEvidenceAccess
from .pilot_v05 import pilot_enabled, purchase_for_code, validate_purchase, owned_program, aware
from .security import merchant_actor, customer_actor, decode

router = APIRouter(tags=['Pruvs v0.6 Receipt Review'])
MAX_IMAGE = 180_000

class EvidenceIn(BaseModel):
    consent: bool
    merchant_label: str = Field(min_length=1, max_length=160)
    receipt_date: str = Field(default='', max_length=32)
    image_base64: str = Field(min_length=500, max_length=250_000)

class ClaimV06In(BaseModel):
    program_id: str = Field(min_length=36, max_length=36)
    code: str = Field(min_length=24, max_length=24, pattern=r'^[A-Fa-f0-9]{24}$')
    receipt_proof: str = Field(min_length=60, max_length=4096)
    evidence: EvidenceIn


def safe_image(encoded):
    try:
        raw=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):
        raise HTTPException(422,'Invalid receipt preview image') from None
    if not 500 <= len(raw) <= MAX_IMAGE or not raw.startswith(b'\xff\xd8\xff') or not raw.endswith(b'\xff\xd9'):
        raise HTTPException(422,'Receipt preview must be a valid, limited-size JPEG')
    return raw

@router.post('/v1/customer/pilot/claims/v06',status_code=201)
def claim_v06(payload:ClaimV06In,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    pilot_enabled()
    if payload.evidence.consent is not True:
        raise HTTPException(422,'Explicit consent to share this receipt with the selected merchant is required')
    p=db.get(Program,payload.program_id)
    if not p or p.status!='published':raise HTTPException(404,'Program unavailable')
    allowed_merchants={part.strip() for part in os.getenv('PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS','').split(',') if part.strip()}
    if p.merchant_id not in allowed_merchants:
        raise HTTPException(403,'This receipt pilot is not enabled for this merchant')
    member=db.scalar(select(Membership).where(Membership.program_id==p.id,Membership.consumer_id==consumer_id))
    if not member:raise HTTPException(403,'Join the program before claiming')
    row=purchase_for_code(db,payload);validate_purchase(row,p.id)
    proof=decode(payload.receipt_proof,get_settings().pruvs_bridge_secret,
                 'pruvs-core','pruvs-business','receipt_proof_v06')
    if proof.get('sub')!=consumer_id or proof.get('store_id')!=p.store_id or proof.get('currency')!=p.currency:
        raise HTTPException(403,'Receipt verification mismatch')
    amount=proof.get('amount_minor')
    if type(amount) is not int or amount!=row.amount_minor or amount<p.min_purchase_minor:
        raise HTTPException(422,'Receipt amount does not match merchant purchase code')
    rid=proof.get('receipt_id')
    if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{64}',rid):
        raise HTTPException(422,'Invalid receipt reference')
    img=safe_image(payload.evidence.image_base64)
    sha=hashlib.sha256(img).hexdigest()
    if proof.get('evidence_sha256')!=sha or proof.get('consent') is not True:
        raise HTTPException(403,'Receipt preview is not authenticated by Pruvs Core')
    merchant_label=payload.evidence.merchant_label.strip()
    if not merchant_label:raise HTTPException(422,'Merchant name is required')
    if (proof.get('merchant_label')!=merchant_label or
            proof.get('receipt_date','')!=payload.evidence.receipt_date):
        raise HTTPException(403,'Receipt metadata differs from the verified submission')
    claim=ReceiptClaim(merchant_id=p.merchant_id,program_id=p.id,consumer_id=consumer_id,
                 external_receipt_id=rid,amount_minor=amount,source_system='pruvs',status='pending')
    try:
        db.add(claim);db.flush()
        db.add(ReceiptEvidence(claim_id=claim.id,merchant_id=p.merchant_id,
                  merchant_label=merchant_label,receipt_date=payload.evidence.receipt_date,
                  image_jpeg=img,image_sha256=sha))
        row.claim_id=claim.id
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'This receipt or purchase code has already been used') from None
    return {'claim_id':claim.id,'status':'pending',
            'message':'Receipt submitted to the merchant for review. No stamps yet.'}

@router.get('/v1/merchant/claims/{claim_id}/evidence')
def merchant_evidence(claim_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    claim=db.scalar(select(ReceiptClaim).where(ReceiptClaim.id==claim_id,
                             ReceiptClaim.merchant_id==staff.merchant_id))
    if not claim:raise HTTPException(404,'Receipt claim not found')
    from .pilot_v12 import require_code_unlock
    require_code_unlock(db,claim,staff)
    ev=db.get(ReceiptEvidence,claim_id)
    if not ev or ev.merchant_id!=staff.merchant_id:raise HTTPException(404,'No consented receipt preview available')
    if claim.status!='pending':raise HTTPException(409,'Receipt preview is available only while review is pending')
    if aware(ev.created_at)<utcnow()-timedelta(days=int(os.getenv('PRUVS_RECEIPT_EVIDENCE_RETENTION_DAYS','30'))):
        raise HTTPException(410,'Receipt preview has expired')
    # Only authenticated staff belonging to this merchant can inspect the snapshot.
    db.add(ReceiptEvidenceAccess(claim_id=claim.id,staff_id=staff.id,
                 merchant_id=staff.merchant_id,action='view'))
    db.commit()
    program=db.get(Program,claim.program_id)
    store=db.get(Store,program.store_id) if program else None
    return JSONResponse(content={'claim_id':claim.id,'status':claim.status,'program_title':program.title if program else '',
            'store_name':store.name if store else '',
            'amount_minor':claim.amount_minor,'currency':program.currency if program else 'RON',
            'merchant_label':ev.merchant_label,'receipt_date':ev.receipt_date,
            'consented_at':ev.consent_at.isoformat(),
            'image_mime':'image/jpeg','image_base64':base64.b64encode(ev.image_jpeg).decode('ascii'),
            'disclaimer':'Merchant must compare this receipt with its own completed sale records. OCR is not payment verification.'},headers={'Cache-Control':'no-store','Pragma':'no-cache'})

@router.get('/v1/customer/pilot/claims')
def my_pilot_claims(consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    # Excludes merchant evidence, merchant staff details and images.
    rows=db.scalars(select(ReceiptClaim).where(ReceiptClaim.consumer_id==consumer_id)
                     .order_by(ReceiptClaim.created_at.desc()).limit(100)).all()
    return [{'claim_id':c.id,'receipt_ref':c.external_receipt_id,'program_id':c.program_id,
             'status':c.status,'amount_minor':c.amount_minor,
             'submitted_at':c.created_at.isoformat(),
             'rejection_reason':(db.get(ReceiptEvidence,c.id).rejection_reason if c.status=='rejected' and db.get(ReceiptEvidence,c.id) else '')} for c in rows]


def approval_guard(db,claim,staff):
    """Called from existing approval/rejection paths; no review bypass via old API."""
    if claim.source_system!='pruvs':
        return
    ev=db.get(ReceiptEvidence,claim.id)
    # Every v0.6 claim requires review even while legacy v0.5 claims remain
    # supported during the independent deployment sequence.
    require_all=os.getenv('PRUVS_BUSINESS_V06_REQUIRE_EVIDENCE','false').lower()=='true'
    if ev is None and not require_all:
        return
    if not ev or ev.merchant_id!=staff.merchant_id:
        raise HTTPException(409,'Receipt evidence missing; ask customer to resubmit in v0.6')
    if aware(ev.created_at)<utcnow()-timedelta(days=int(os.getenv('PRUVS_RECEIPT_EVIDENCE_RETENTION_DAYS','30'))):
        raise HTTPException(409,'Receipt review window has expired')
    review=db.scalar(select(ReceiptEvidenceAccess).where(
               ReceiptEvidenceAccess.claim_id==claim.id,
               ReceiptEvidenceAccess.staff_id==staff.id,
               ReceiptEvidenceAccess.action=='view')
               .order_by(ReceiptEvidenceAccess.at.desc()).limit(1))
    if not review or aware(review.at)<utcnow()-timedelta(minutes=15):
        raise HTTPException(409,'Open and review the receipt before approving or rejecting')
    # A rotated customer code invalidates earlier review authorization.
    # Receipt-evidence "view" events alone cannot bypass current code unlock.
    from .pilot_v12 import require_code_unlock
    require_code_unlock(db,claim,staff)
    db.add(ReceiptEvidenceAccess(claim_id=claim.id,staff_id=staff.id,
                 merchant_id=staff.merchant_id,action='decision'))
