"""Pruvs Business v0.5: scoped merchant promotions and merchant-approved receipt pilot.

No SIBS/POS connectivity; purchase codes are issued manually by merchant staff AFTER checkout.
Only explicit published promotions are publicly discoverable. No OCR-only automatic credits.
"""
import hashlib
import os
import re
import secrets
from urllib.parse import urlsplit
from datetime import timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import (Merchant, Staff, Store, Program, Membership, ReceiptClaim,
                     Promotion, PurchaseCode, utcnow)
from .security import merchant_actor, customer_actor, decode

router=APIRouter(tags=['Pruvs v0.5 Pilot'])

def can_manage(staff):
    if staff.role not in ('owner','manager'):
        raise HTTPException(403,'Merchant manager role required')

def owned_program(db, staff, program_id):
    p=db.get(Program,program_id)
    if not p or p.merchant_id != staff.merchant_id:raise HTTPException(404,'Program not found')
    return p

def aware(dt):
    if dt is None:return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

def campaign_schema_ready(db):
    """Fail closed with a controlled 503 if the staging media migration is missing."""
    from sqlalchemy import inspect
    try:
        inspector = inspect(db.get_bind())
        if not inspector.has_table('loyalty_promotions'):
            raise HTTPException(503,'Campaign media schema is not ready. Apply the reviewed staging migration.')
        columns={c['name'] for c in inspector.get_columns('loyalty_promotions')}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503,'Campaign storage database is temporarily unavailable.') from None
    if not {'media_url','media_type','media_alt'}.issubset(columns):
        raise HTTPException(503,'Campaign media schema is not migrated. Contact the staging administrator.')

def pilot_enabled():
    if os.getenv('PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED','false').lower() != 'true':
        raise HTTPException(503,'Receipt verification pilot is not enabled.')

def promo_json(p,db):
    program=db.get(Program,p.program_id)
    store=db.get(Store,program.store_id) if program else None
    merchant=db.get(Merchant,p.merchant_id)
    return {'id':p.id,'merchant_name':merchant.name if merchant else '',
            'store_name':store.name if store else '', 'store_address':store.address if store else '',
            'program_id':p.program_id,'program_title':program.title if program else '',
            'stamps_required':program.stamps_required if program else 0,
            'min_purchase_minor':program.min_purchase_minor if program else 0,
            'reward_minor':program.reward_minor if program else 0,
            'currency':program.currency if program else 'RON',
            'headline':p.headline,'message':p.message,'status':p.status,
            'media_url':p.media_url,'media_type':p.media_type,'media_alt':p.media_alt,
            'expires_at':p.expires_at.isoformat() if p.expires_at else None}

class PromotionIn(BaseModel):
    program_id: str
    headline: str=Field(min_length=5,max_length=100)
    message: str=Field(min_length=10,max_length=500)
    duration_days: int=Field(default=14,ge=1,le=90)
    media_url: str|None = Field(default=None,max_length=900)
    media_type: str|None = Field(default=None,max_length=40)
    media_alt: str|None = Field(default=None,max_length=160)

def campaign_media(payload):
    if not payload.media_url:return None,None,None
    uri=urlsplit(payload.media_url)
    allowed={h.strip().lower() for h in os.getenv('PRUVS_CAMPAIGN_MEDIA_HOSTS','').split(',') if h.strip()}
    if (uri.scheme!='https' or uri.hostname not in allowed or uri.username or uri.password
            or uri.port not in (None,443) or not allowed or not uri.path or uri.fragment):
        raise HTTPException(422,'Campaign asset must use an approved HTTPS media host')
    if payload.media_type not in ('image/jpeg','image/png','image/webp','image/gif','video/mp4','video/webm'):
        raise HTTPException(422,'Campaign image, GIF or video type is unsupported')
    return payload.media_url,payload.media_type,payload.media_alt or ''

@router.get('/v1/merchant/promotions')
def merchant_promotions(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    rows=db.scalars(select(Promotion).where(Promotion.merchant_id==staff.merchant_id)
                    .order_by(Promotion.created_at.desc()).limit(100)).all()
    return [promo_json(p,db) for p in rows]

@router.post('/v1/merchant/promotions',status_code=201)
def merchant_create_promo(payload:PromotionIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    can_manage(staff)
    program=owned_program(db,staff,payload.program_id)
    if program.status!='published':raise HTTPException(409,'Publish the loyalty program first.')
    media_url,media_type,media_alt=campaign_media(payload)
    promo=Promotion(merchant_id=staff.merchant_id,program_id=program.id,
                    headline=payload.headline.strip(),message=payload.message.strip(),
                    media_url=media_url,media_type=media_type,media_alt=media_alt,
                    status='draft',duration_days=payload.duration_days)
    db.add(promo);db.commit();db.refresh(promo)
    return promo_json(promo,db)

@router.post('/v1/merchant/promotions/{promotion_id}/publish')
def publish_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    can_manage(staff)
    p=db.get(Promotion,promotion_id)
    if not p or p.merchant_id!=staff.merchant_id:raise HTTPException(404,'Promotion not found')
    program=owned_program(db,staff,p.program_id)
    if program.status!='published':raise HTTPException(409,'Program is not published')
    if p.status!='draft':raise HTTPException(409,'Only drafts may be published')
    p.status='published';p.published_at=utcnow()
    p.expires_at=utcnow()+timedelta(days=p.duration_days)
    db.commit();return promo_json(p,db)

@router.post('/v1/merchant/promotions/{promotion_id}/unpublish')
def unpublish_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    can_manage(staff)
    p=db.get(Promotion,promotion_id)
    if not p or p.merchant_id!=staff.merchant_id:raise HTTPException(404,'Promotion not found')
    if p.status!='published':raise HTTPException(409,'Only live promotions may be unpublished')
    p.status='paused';db.commit();return promo_json(p,db)

@router.get('/v1/promotions')
def public_promotions(limit:int=Query(12,ge=1,le=30),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    # No draft, expired, inactive merchant, inactive store or unpublished-program exposure.
    now=utcnow()
    rows=db.scalars(select(Promotion).where(Promotion.status=='published')
                    .order_by(Promotion.published_at.desc()).limit(200)).all()
    data=[]
    for p in rows:
        if not p.expires_at or aware(p.expires_at)<=now:continue
        program=db.get(Program,p.program_id)
        if not program or program.status!='published':continue
        merchant=db.get(Merchant,p.merchant_id)
        store=db.get(Store,program.store_id)
        if not merchant or merchant.status!='active' or not store or not store.active:continue
        data.append(promo_json(p,db))
        if len(data)>=limit:break
    return data

class IssuePurchaseIn(BaseModel):
    program_id: str
    amount_minor: int=Field(ge=1,le=10000000)

class CodeIn(BaseModel):
    program_id: str
    code: str=Field(min_length=24,max_length=24,pattern=r'^[A-Fa-f0-9]{24}$')

class ClaimIn(CodeIn):
    receipt_proof: str=Field(min_length=60,max_length=4096)

def purchase_for_code(db,payload):
    code_hash=hashlib.sha256(payload.code.upper().encode('ascii')).hexdigest()
    return db.scalar(select(PurchaseCode).where(PurchaseCode.code_hash==code_hash).with_for_update())

def validate_purchase(row,program_id):
    if not row or row.program_id!=program_id or row.claim_id is not None or aware(row.expires_at)<=utcnow():
        raise HTTPException(404,'Purchase code invalid, expired or already used.')

@router.post('/v1/merchant/pilot/purchases/issue',status_code=201)
def issue_purchase(payload:IssuePurchaseIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    pilot_enabled();can_manage(staff)
    p=owned_program(db,staff,payload.program_id)
    if p.status!='published':raise HTTPException(409,'Program must be published')
    from .pilot_enrollment_v0612 import db_mode_enabled, merchant_pilot_allowed
    if db_mode_enabled() and not merchant_pilot_allowed(db,p.merchant_id):
        raise HTTPException(403,'Merchant receipt pilot is not approved')
    if payload.amount_minor<p.min_purchase_minor:raise HTTPException(422,'Purchase below loyalty minimum')
    store=db.get(Store,p.store_id)
    if not store or not store.active:raise HTTPException(409,'Store inactive')
    # 96-bit unpredictable code, never persisted in plaintext; issue ONLY after completed checkout.
    code=secrets.token_hex(12).upper()
    row=PurchaseCode(merchant_id=staff.merchant_id,program_id=p.id,
                     code_hash=hashlib.sha256(code.encode()).hexdigest(),
                     amount_minor=payload.amount_minor,expires_at=utcnow()+timedelta(minutes=30))
    db.add(row);db.commit()
    return {'purchase_code':code,'expires_at':row.expires_at.isoformat(),
            'amount_minor':row.amount_minor,'currency':p.currency,
            'message':'Give this one-use code to the customer after the completed sale.'}

@router.post('/v1/customer/pilot/purchases/preview')
def preview_purchase(payload:CodeIn,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    pilot_enabled()
    p=db.get(Program,payload.program_id)
    if not p or p.status!='published':raise HTTPException(404,'Program unavailable')
    from .pilot_enrollment_v0612 import db_mode_enabled, merchant_pilot_allowed
    if db_mode_enabled() and not merchant_pilot_allowed(db,p.merchant_id):
        raise HTTPException(403,'Merchant receipt pilot is not approved')
    member=db.scalar(select(Membership).where(Membership.program_id==p.id,Membership.consumer_id==consumer_id))
    if not member:raise HTTPException(403,'Join the program before claiming')
    row=purchase_for_code(db,payload);validate_purchase(row,p.id)
    store=db.get(Store,p.store_id)
    return {'store_id':p.store_id,'store_name':store.name if store else '',
            'amount_minor':row.amount_minor,'currency':p.currency}

@router.post('/v1/customer/pilot/claims',status_code=201)
def claim_purchase(payload:ClaimIn,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    pilot_enabled()
    if os.getenv('PRUVS_BUSINESS_V06_REQUIRE_EVIDENCE','false').lower()=='true':
        raise HTTPException(409,'Use the updated v0.6 receipt submission flow.')
    p=db.get(Program,payload.program_id)
    if not p or p.status!='published':raise HTTPException(404,'Program unavailable')
    from .pilot_enrollment_v0612 import db_mode_enabled, merchant_pilot_allowed
    if db_mode_enabled() and not merchant_pilot_allowed(db,p.merchant_id):
        raise HTTPException(403,'Merchant receipt pilot is not approved')
    member=db.scalar(select(Membership).where(Membership.program_id==p.id,Membership.consumer_id==consumer_id))
    if not member:raise HTTPException(403,'Join the program first')
    row=purchase_for_code(db,payload);validate_purchase(row,p.id)
    proof=decode(payload.receipt_proof,get_settings().pruvs_bridge_secret,'pruvs-core','pruvs-business','receipt_proof')
    if proof.get('sub')!=consumer_id or proof.get('store_id')!=p.store_id or proof.get('currency')!=p.currency:
        raise HTTPException(403,'Receipt verification mismatch')
    amt=proof.get('amount_minor')
    if type(amt) is not int or amt!=row.amount_minor or amt<p.min_purchase_minor:
        raise HTTPException(422,'Receipt amount does not match verified purchase code')
    rid=proof.get('receipt_id')
    if not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{64}',rid):
        raise HTTPException(422,'Invalid receipt reference')
    c=ReceiptClaim(merchant_id=p.merchant_id,program_id=p.id,consumer_id=consumer_id,
                   external_receipt_id=rid,amount_minor=amt,source_system='pruvs',status='pending')
    try:
        db.add(c);db.flush();row.claim_id=c.id
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Receipt or purchase code already used') from None
    return {'claim_id':c.id,'status':'pending',
            'message':'Merchant approval required. No stamps have been credited.'}
