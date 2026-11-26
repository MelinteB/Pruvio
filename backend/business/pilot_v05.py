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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
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

def program_is_discoverable(program, merchant, store):
    return bool(
        program and program.status == 'published'
        and merchant and merchant.status == 'active'
        and store and store.active
        and merchant.id == program.merchant_id == store.merchant_id
    )

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

def _promo_google_place_id(db,store):
    if not store:return None
    from .google_places_v0618 import linked_place_id
    return linked_place_id(db,store.id)


def promo_json(p,db,*,now=None,acquisition_ready=None,include_media_keys=False):
    now=now or utcnow()
    program=db.get(Program,p.program_id)
    if program and program.merchant_id != p.merchant_id:
        program=None
    store=db.get(Store,program.store_id) if program else None
    if store and store.merchant_id != p.merchant_id:
        store=None
    merchant=db.get(Merchant,p.merchant_id)
    from .pilot_readiness_v069 import merchant_acquisition_ready
    if acquisition_ready is None:
        acquisition_ready = merchant_acquisition_ready(db,p.merchant_id)
    created=aware(p.created_at)
    published=aware(p.published_at)
    expires=aware(p.expires_at)
    from .campaign_gallery_v0624 import gallery_assets
    assets=gallery_assets(db,p)
    result={'id':p.id,
            'gallery':assets,
            'created_at':created.isoformat() if created else None,
            'published_at':published.isoformat() if published else None,
            'merchant_name':merchant.name if merchant else '',
            'store_latitude':store.latitude if store else None,
            'store_longitude':store.longitude if store else None,
            'google_place_id':_promo_google_place_id(db,store),
            'store_name':store.name if store else '', 'store_address':store.address if store else '',
            'program_id':p.program_id,'program_title':program.title if program else '',
            'stamps_required':program.stamps_required if program else 0,
            'min_purchase_minor':program.min_purchase_minor if program else 0,
            'reward_minor':program.reward_minor if program else 0,
            'currency':program.currency if program else 'RON',
            'headline':p.headline,'message':p.message,'status':p.status,
            'is_live':bool(p.status=='published' and expires and expires>now
                           and (published is None or published<=now)
                           and program_is_discoverable(program,merchant,store) and acquisition_ready),
            'receipt_activation_ready':bool(acquisition_ready),
            'media_url':p.media_url,'media_type':p.media_type,'media_alt':p.media_alt,
            'expires_at':expires.isoformat() if expires else None,
            'duration_days':p.duration_days}
    if include_media_keys:
        from .media_assets_v0725 import promotion_media_assets
        result['media_assets']=promotion_media_assets(db,p.merchant_id,p.id)
    return result

class PromotionIn(BaseModel):
    program_id: str
    headline: str=Field(min_length=5,max_length=100)
    message: str=Field(min_length=10,max_length=500)
    duration_days: int=Field(default=14,ge=1,le=90)
    media_url: str|None = Field(default=None,max_length=900)
    media_type: str|None = Field(default=None,max_length=40)
    media_alt: str|None = Field(default=None,max_length=160)
    gallery_keys: list[str]|None = Field(default=None,max_length=5)
    media_key: str|None = Field(default=None,max_length=500)
    rendered_media_key: str|None = Field(default=None,max_length=500)

    @field_validator('headline','message',mode='before')
    @classmethod
    def trim_campaign_copy(cls,value):
        return value.strip() if isinstance(value,str) else value

def campaign_media(payload):
    if not payload.media_url:return None,None,None
    try:
        uri=urlsplit(payload.media_url)
        port=uri.port
    except ValueError:
        raise HTTPException(422,'Campaign asset must use an approved HTTPS media host') from None
    allowed={h.strip().lower() for h in os.getenv('PRUVS_CAMPAIGN_MEDIA_HOSTS','').split(',') if h.strip()}
    if (uri.scheme!='https' or uri.hostname not in allowed or uri.username or uri.password
            or port not in (None,443) or not allowed or not uri.path or uri.fragment):
        raise HTTPException(422,'Campaign asset must use an approved HTTPS media host')
    if payload.media_type not in ('image/jpeg','image/png','image/webp','image/gif','video/mp4','video/webm'):
        raise HTTPException(422,'Campaign image, GIF or video type is unsupported')
    return payload.media_url,payload.media_type,payload.media_alt or ''

@router.get('/v1/merchant/promotions')
def merchant_promotions(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    rows=db.scalars(select(Promotion).where(Promotion.merchant_id==staff.merchant_id)
                    .order_by(Promotion.created_at.desc()).limit(100)).all()
    now=utcnow()
    return [promo_json(p,db,now=now,include_media_keys=True) for p in rows]

@router.post('/v1/merchant/promotions',status_code=201)
def merchant_create_promo(payload:PromotionIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    can_manage(staff)
    program=owned_program(db,staff,payload.program_id)
    if program.status!='published':raise HTTPException(409,'Publish the loyalty program first.')
    from .campaign_gallery_v0624 import validate_gallery, save_gallery
    assets=validate_gallery(db,staff,payload.gallery_keys,payload.media_alt)
    from .campaign_copy_v0624 import validate_campaign_copy
    try:validate_campaign_copy(payload.headline,payload.message)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    media_url,media_type,media_alt=campaign_media(payload)
    if assets:
        media_url,media_type,media_alt=(assets[0][k] for k in ('media_url','media_type','media_alt'))
    promo=Promotion(merchant_id=staff.merchant_id,program_id=program.id,
                    headline=payload.headline,message=payload.message,
                    media_url=media_url,media_type=media_type,media_alt=media_alt,
                    status='draft',duration_days=payload.duration_days)
    db.add(promo);db.flush()
    if assets:save_gallery(db,promo,assets)
    from .media_assets_v0725 import set_promotion_media
    set_promotion_media(db,staff.merchant_id,promo.id,
        list(payload.gallery_keys or []) + [key for key in (payload.media_key,payload.rendered_media_key) if key])
    db.commit();db.refresh(promo)
    return promo_json(promo,db,include_media_keys=True)

@router.patch('/v1/merchant/promotions/{promotion_id}')
def update_promotion_draft(promotion_id:str,payload:PromotionIn,
                           staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    """Allow editing only merchant-owned, unpublished drafts."""
    campaign_schema_ready(db)
    can_manage(staff)
    promo=owned_campaign(db,staff,promotion_id)
    if promo.status!='draft':
        raise HTTPException(409,'Only unpublished drafts may be edited; copy the offer instead.')
    program=owned_program(db,staff,promo.program_id)
    if program.status!='published' or payload.program_id!=promo.program_id:
        raise HTTPException(409,'Keep the original published loyalty program for this draft.')
    from .campaign_gallery_v0624 import validate_gallery, save_gallery, gallery_assets
    assets=(gallery_assets(db,promo) if payload.gallery_keys is None
            else validate_gallery(db,staff,payload.gallery_keys,payload.media_alt))
    from .campaign_copy_v0624 import validate_campaign_copy
    try:validate_campaign_copy(payload.headline,payload.message)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    media_url,media_type,media_alt=campaign_media(payload)
    if assets:
        media_url,media_type,media_alt=(assets[0][k] for k in ('media_url','media_type','media_alt'))
    if payload.gallery_keys is not None:save_gallery(db,promo,assets)
    from .media_assets_v0725 import set_promotion_media
    if payload.model_fields_set.intersection({'gallery_keys','media_key','rendered_media_key'}):
        set_promotion_media(db,staff.merchant_id,promo.id,
            list(payload.gallery_keys or []) + [key for key in (payload.media_key,payload.rendered_media_key) if key])
    promo.headline=payload.headline
    promo.message=payload.message
    promo.duration_days=payload.duration_days
    promo.media_url=media_url
    promo.media_type=media_type
    promo.media_alt=media_alt
    db.commit()
    return promo_json(promo,db,include_media_keys=True)


@router.post('/v1/merchant/promotions/{promotion_id}/publish')
def publish_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    can_manage(staff)
    p=owned_campaign(db,staff,promotion_id)
    if p.status!='draft':raise HTTPException(409,'Only drafts may be published')
    require_publishable_campaign(db,staff,p)
    now=utcnow()
    p.status='published';p.published_at=now
    p.expires_at=now+timedelta(days=p.duration_days)
    db.commit();return promo_json(p,db,include_media_keys=True)

@router.post('/v1/merchant/promotions/{promotion_id}/republish')
def republish_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),
                        db:Session=Depends(get_db)):
    """Explicitly republish a paused or expired offer without a duplicate draft."""
    campaign_schema_ready(db)
    can_manage(staff)
    p=owned_campaign(db,staff,promotion_id)
    now=utcnow()
    ended=(p.status=='published' and (p.expires_at is None or aware(p.expires_at)<=now))
    if p.status!='paused' and not ended:
        raise HTTPException(409,'Only paused or expired promotions may be republished.')
    require_publishable_campaign(db,staff,p)
    p.status='published'
    p.published_at=now
    p.expires_at=now+timedelta(days=p.duration_days)
    db.commit()
    return promo_json(p,db,include_media_keys=True)


@router.post('/v1/merchant/promotions/{promotion_id}/unpublish')
def unpublish_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    can_manage(staff)
    p=owned_campaign(db,staff,promotion_id)
    if p.status!='published':raise HTTPException(409,'Only live promotions may be unpublished')
    p.status='paused';db.commit();return promo_json(p,db,include_media_keys=True)

def owned_campaign(db:Session,staff:Staff,promotion_id:str)->Promotion:
    promotion=db.scalar(
        select(Promotion)
        .where(Promotion.id==promotion_id, Promotion.merchant_id==staff.merchant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if promotion is None:
        raise HTTPException(404,'Promotion not found')
    return promotion


def can_reopen_program(db:Session,staff:Staff,promotion:Promotion)->Program:
    program=owned_program(db,staff,promotion.program_id)
    if program.status!='published':
        raise HTTPException(409,'The linked loyalty program must be published first.')
    return program


def require_publishable_campaign(db:Session,staff:Staff,promotion:Promotion)->None:
    program=can_reopen_program(db,staff,promotion)
    merchant=db.get(Merchant,program.merchant_id)
    store=db.get(Store,program.store_id)
    if not program_is_discoverable(program,merchant,store):
        raise HTTPException(409,'An active merchant and location are required to publish a campaign.')
    # Every current campaign is linked to a published loyalty program whose reward
    # requires merchant-verified qualifying purchases. Keep this gate for those
    # receipt-based rewards and return actionable readiness details to the editor.
    from .pilot_readiness_v069 import acquisition_gate_enabled, merchant_receipt_report
    if acquisition_gate_enabled():
        readiness = merchant_receipt_report(db, staff.merchant_id)
        if not readiness.get('receipt_review_ready'):
            raise HTTPException(409, detail={
                'code': 'RECEIPT_ACTIVATION_INCOMPLETE',
                'message': 'Receipt rewards are not active for this merchant. The campaign remains a draft. Check the activation checklist under Loyalty.',
                'blocked_by': readiness.get('blocked_by', []),
            })


@router.post('/v1/merchant/promotions/{promotion_id}/reopen')
def reopen_unpublished_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    """A paused (unpublished) promotion returns to editable draft state."""
    campaign_schema_ready(db)
    can_manage(staff)
    promotion=owned_campaign(db,staff,promotion_id)
    if promotion.status!='paused':
        raise HTTPException(409,'Only paused promotions may be reopened for editing.')
    can_reopen_program(db,staff,promotion)
    promotion.status='draft'
    promotion.published_at=None
    promotion.expires_at=None
    db.commit()
    return promo_json(promotion,db,include_media_keys=True)


@router.post('/v1/merchant/promotions/{promotion_id}/archive')
def archive_unpublished_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    """Archive only unpublished or already-expired promotions. Never silently hide live offers."""
    campaign_schema_ready(db)
    can_manage(staff)
    promotion=owned_campaign(db,staff,promotion_id)
    expired=(
        promotion.status=='published' and promotion.expires_at is not None
        and aware(promotion.expires_at)<=utcnow()
    )
    if promotion.status not in ('draft','paused') and not expired:
        raise HTTPException(409,'Unpublish the live campaign before archiving it.')
    promotion.status='archived'
    db.commit()
    return promo_json(promotion,db,include_media_keys=True)


@router.post('/v1/merchant/promotions/{promotion_id}/restore')
def restore_archived_promotion(promotion_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    """Restore an archived offer as a draft; it never republishes automatically."""
    campaign_schema_ready(db)
    can_manage(staff)
    promotion=owned_campaign(db,staff,promotion_id)
    if promotion.status!='archived':
        raise HTTPException(409,'Only archived promotions may be restored.')
    can_reopen_program(db,staff,promotion)
    promotion.status='draft'
    promotion.published_at=None
    promotion.expires_at=None
    db.commit()
    return promo_json(promotion,db,include_media_keys=True)


@router.get('/v1/promotions')
def public_promotions(limit:int=Query(12,ge=1,le=30),db:Session=Depends(get_db)):
    campaign_schema_ready(db)
    # Filter *before* limiting. A backlog of paused/expired rows must not
    # crowd live campaigns out of the customer's feed.
    now=utcnow()
    rows=db.scalars(
        select(Promotion)
        .join(Program,Promotion.program_id==Program.id)
        .join(Merchant,Promotion.merchant_id==Merchant.id)
        .join(Store,Program.store_id==Store.id)
        .where(Promotion.status=='published',
               or_(Promotion.published_at.is_(None),Promotion.published_at<=now),
               Promotion.expires_at.is_not(None),
               Promotion.expires_at>now,
               Program.status=='published',
               Program.merchant_id==Merchant.id,
               Merchant.status=='active',
               Store.merchant_id==Merchant.id,Store.active.is_(True))
        .order_by(Promotion.published_at.desc(),Promotion.id.desc())
    ).all()
    from .pilot_readiness_v069 import merchant_acquisition_ready
    result=[]; eligibility={}
    for p in rows:
        if p.merchant_id not in eligibility:
            eligibility[p.merchant_id]=merchant_acquisition_ready(db,p.merchant_id)
        if eligibility[p.merchant_id]:
            result.append(promo_json(p,db,now=now,acquisition_ready=True))
        if len(result)>=limit:break
    return result

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
