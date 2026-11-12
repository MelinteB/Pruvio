"""Customer-issued receipt verification codes (v1.2, staging pilot only).
Merchant must inspect consented image; code lookup does not credit stamps.
"""
import hashlib
import os
import re
from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .config import get_settings
from .models import Program,Membership,ReceiptClaim,Store,Staff,utcnow
from .models_v06 import ReceiptEvidence
from .models_v12 import CustomerClaimCode
from .pilot_v05 import pilot_enabled,aware
from .pilot_v06 import EvidenceIn,safe_image
from .security import merchant_actor,customer_actor,decode
router=APIRouter(tags=['Pruvs v1.2 customer claim codes'])

def ready():
    pilot_enabled()
    if os.getenv('PRUVS_BUSINESS_CUSTOMER_CODES_V12_ENABLED','false').lower()!='true':
        raise HTTPException(503,'Customer receipt codes pilot is not enabled')

def merchant_pilot_allowed(merchant_id):
    return merchant_id in {v.strip() for v in os.getenv('PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS','').split(',') if v.strip()}

class CustomerClaimIn(BaseModel):
    program_id:str=Field(min_length=36,max_length=36)
    code_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    receipt_proof:str=Field(min_length=60,max_length=4096)
    evidence:EvidenceIn

class CodeLookup(BaseModel):
    code:str=Field(min_length=24,max_length=40)

@router.get('/v1/customer/pilot/programs/{program_id}/receipt-eligibility-v12')
def eligible(program_id:str,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    ready()
    p=db.get(Program,program_id)
    if not p or p.status!='published' or not merchant_pilot_allowed(p.merchant_id):
        raise HTTPException(404,'Program not available for receipt-code pilot')
    member=db.scalar(select(Membership).where(Membership.program_id==p.id,Membership.consumer_id==consumer_id))
    if not member:raise HTTPException(403,'Join the loyalty program before claiming')
    store=db.get(Store,p.store_id)
    if not store or not store.active:raise HTTPException(409,'Store unavailable')
    return {'store_id':p.store_id,'currency':p.currency,'min_purchase_minor':p.min_purchase_minor}

@router.post('/v1/customer/pilot/claims/v12/customer-code',status_code=201)
def create_customer_code(payload:CustomerClaimIn,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    ready()
    p=db.get(Program,payload.program_id)
    if not p or p.status!='published' or not merchant_pilot_allowed(p.merchant_id):
        raise HTTPException(404,'Program unavailable')
    member=db.scalar(select(Membership).where(Membership.program_id==p.id,Membership.consumer_id==consumer_id))
    if not member:raise HTTPException(403,'Join the loyalty program first')
    if payload.evidence.consent is not True:raise HTTPException(422,'Explicit receipt-sharing consent required')
    proof=decode(payload.receipt_proof,get_settings().pruvs_bridge_secret,
                 'pruvs-core','pruvs-business','receipt_proof_v06')
    if (proof.get('sub')!=consumer_id or proof.get('store_id')!=p.store_id
        or proof.get('currency')!=p.currency or proof.get('consent') is not True):
        raise HTTPException(403,'Receipt verification mismatch')
    amount=proof.get('amount_minor')
    if type(amount) is not int or amount<=0 or amount>10_000_000 or amount<p.min_purchase_minor:
        raise HTTPException(422,'Receipt amount not eligible')
    rid=proof.get('receipt_id')
    if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{64}',rid):
        raise HTTPException(422,'Invalid receipt reference')
    img=safe_image(payload.evidence.image_base64)
    sha=hashlib.sha256(img).hexdigest()
    label=payload.evidence.merchant_label.strip()
    if (proof.get('evidence_sha256')!=sha or proof.get('merchant_label')!=label
        or proof.get('receipt_date','')!=payload.evidence.receipt_date):
        raise HTTPException(403,'Receipt preview differs from consented signed evidence')
    existing=db.scalar(select(ReceiptClaim).where(ReceiptClaim.source_system=='pruvs',
                                             ReceiptClaim.external_receipt_id==rid).with_for_update())
    expiry=utcnow()+timedelta(minutes=20)
    if existing:
        if (existing.consumer_id!=consumer_id or existing.program_id!=p.id or existing.status!='pending'):
            raise HTTPException(409,'Receipt already claimed')
        code=db.get(CustomerClaimCode,existing.id)
        if not code:raise HTTPException(409,'Use the existing merchant receipt verification flow')
        code.code_hash=payload.code_hash;code.expires_at=expiry
        code.unlocked_by_staff=None;code.unlocked_at=None
        db.commit()
        return {'claim_id':existing.id,'status':'pending','expires_at':expiry.isoformat(),'rotated':True}
    claim=ReceiptClaim(merchant_id=p.merchant_id,program_id=p.id,consumer_id=consumer_id,
                       external_receipt_id=rid,amount_minor=amount,source_system='pruvs',status='pending')
    try:
        db.add(claim);db.flush()
        db.add(ReceiptEvidence(claim_id=claim.id,merchant_id=p.merchant_id,
          merchant_label=label,receipt_date=payload.evidence.receipt_date,image_jpeg=img,image_sha256=sha))
        db.add(CustomerClaimCode(claim_id=claim.id,merchant_id=p.merchant_id,
          code_hash=payload.code_hash,expires_at=expiry))
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Receipt already claimed or code conflict') from None
    return {'claim_id':claim.id,'status':'pending','expires_at':expiry.isoformat()}

@router.post('/v1/merchant/claims/customer-code-v12/lookup')
def lookup_customer_code(body:CodeLookup,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    ready()
    code=body.code.replace('-','').strip().upper()
    if code.startswith('PRV'):code=code[3:]
    if not re.fullmatch('[A-F0-9]{24}',code):raise HTTPException(404,'Invalid or expired receipt claim code')
    digest=hashlib.sha256(('v12:'+code).encode('ascii')).hexdigest()
    row=db.scalar(select(CustomerClaimCode).where(CustomerClaimCode.code_hash==digest,
                        CustomerClaimCode.merchant_id==staff.merchant_id).with_for_update())
    if not row or aware(row.expires_at)<utcnow():
        raise HTTPException(404,'Invalid or expired receipt claim code')
    claim=db.get(ReceiptClaim,row.claim_id)
    if not claim or claim.status!='pending' or claim.merchant_id!=staff.merchant_id:
        raise HTTPException(409,'Receipt claim is no longer pending')
    row.unlocked_by_staff=staff.id;row.unlocked_at=utcnow()
    db.commit()
    return {'claim_id':row.claim_id,'status':'pending'}

def require_code_unlock(db,claim,staff):
    row=db.get(CustomerClaimCode,claim.id)
    if row and (row.unlocked_by_staff!=staff.id or not row.unlocked_at or
                aware(row.unlocked_at)<utcnow()-timedelta(minutes=15)):
        raise HTTPException(403,'Enter the customer receipt claim code before viewing the image')
