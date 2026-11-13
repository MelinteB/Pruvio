from datetime import datetime, timezone, timedelta
from math import asin, cos, radians, sin, sqrt
import secrets
import csv
from io import StringIO
from fastapi import Request
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from fastapi.responses import Response
from .db import get_db, engine
from .config import get_settings
from .merchant_enrollment import router as merchant_enrollment_router
from .models import Merchant, Staff, Store, Program, Membership, ReceiptClaim, Reward, Campaign, utcnow
from .models_v067 import DiscountRedemption
from .security import merchant_actor, customer_actor, verify_password, encode_merchant_token, decode
from .schemas import LoginIn, StoreIn, ProgramIn, CampaignGoal, CampaignIn, ReceiptProofIn, ConfirmIn, DemoReceiptIn

settings=get_settings()
app=FastAPI(title='Pruvs Business API',version='0.6.9',docs_url='/docs' if settings.app_env!='production' else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False,
                   allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
app.include_router(merchant_enrollment_router)
from .ai_campaign_v067 import router as ai_campaign_router
app.include_router(ai_campaign_router)
from .media_v067 import router as media_router
app.include_router(media_router)
from .pilot_readiness_v069 import router as receipt_readiness_router
app.include_router(receipt_readiness_router)

def owned(db, cls, object_id, merchant_id):
    item=db.get(cls,object_id)
    if item is None or item.merchant_id!=merchant_id:
        raise HTTPException(404,'Not found')
    return item

def merchant_check(staff):
    if staff.role not in ('owner','manager'):
        raise HTTPException(403,'Merchant manager role required')

def store_json(s):
    return dict(id=s.id,merchant_id=s.merchant_id,name=s.name,address=s.address,
                latitude=s.latitude,longitude=s.longitude,active=s.active)

def program_json(p):
    return dict(id=p.id,store_id=p.store_id,merchant_id=p.merchant_id,title=p.title,
                description=p.description,stamps_required=p.stamps_required,
                min_purchase_minor=p.min_purchase_minor,reward_minor=p.reward_minor,
                currency=p.currency,status=p.status)

def campaign_json(c):
    return dict(id=c.id,title=c.title,goal=c.goal,message=c.message,status=c.status,generator=c.generator)

def dist_km(a,b,c,d):
    R=6371.0088
    lat1,lat2=radians(a),radians(c)
    h=sin((lat2-lat1)/2)**2+cos(lat1)*cos(lat2)*sin(radians(d-b)/2)**2
    return 2*R*asin(min(1,sqrt(h)))

def aware(dt):
    if dt is None:return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

@app.get('/health')
def health():
    return {'service':'Pruvs Business','version':'0.6.9','status':'ok'}

@app.get('/ready', include_in_schema=False)
def readiness():
    # Read only: do not run migrations implicitly in the request path.
    from .schema_readiness import check_schema
    try:
        checks=check_schema(engine())
        if not all(checks.values()):
            return JSONResponse(status_code=503,content={'status':'unavailable','version':'0.6.9'})
        return {'status':'ready','version':'0.6.9'}
    except Exception:
        return JSONResponse(status_code=503,content={'status':'unavailable','version':'0.6.9'})

@app.post('/v1/merchant/login')
def login(payload:LoginIn, db:Session=Depends(get_db)):
    # Do not reveal whether email exists. Add IP/account throttling before public deployment.
    staff=db.scalar(select(Staff).where(Staff.email==payload.email.strip().lower()))
    if not staff or not staff.active or not verify_password(payload.password,staff.password_hash):
        raise HTTPException(401,'Invalid credentials')
    return {'access_token':encode_merchant_token(staff),'token_type':'bearer','expires_in':7200}

@app.get('/v1/merchant/me')
def me(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    m=db.get(Merchant,staff.merchant_id)
    return {'merchant_id':m.id,'merchant_name':m.name,'email':staff.email,'role':staff.role}

@app.get('/v1/merchant/overview')
def overview(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    m=staff.merchant_id
    counts=lambda cls:db.scalar(select(func.count(cls.id)).where(cls.merchant_id==m))
    pending=db.scalar(select(func.count(ReceiptClaim.id)).where(ReceiptClaim.merchant_id==m,ReceiptClaim.status=='pending'))
    redeemed=db.scalar(select(func.count(Reward.id)).where(Reward.merchant_id==m,Reward.status=='redeemed'))
    return {'stores':counts(Store),'programs':counts(Program),'campaigns':counts(Campaign),
            'pending_claims':pending,'redeemed_rewards':redeemed}

@app.get('/v1/merchant/stores')
def get_stores(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    return [store_json(s) for s in db.scalars(select(Store).where(Store.merchant_id==staff.merchant_id)).all()]

@app.post('/v1/merchant/stores',status_code=201)
def add_store(payload:StoreIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    s=Store(merchant_id=staff.merchant_id,**payload.model_dump())
    db.add(s);db.commit();db.refresh(s)
    return store_json(s)

@app.get('/v1/merchant/programs')
def get_programs(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    return [program_json(p) for p in db.scalars(select(Program).where(Program.merchant_id==staff.merchant_id)).all()]

@app.post('/v1/merchant/programs',status_code=201)
def add_program(payload:ProgramIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    owned(db,Store,payload.store_id,staff.merchant_id)
    p=Program(merchant_id=staff.merchant_id,**payload.model_dump())
    db.add(p);db.commit();db.refresh(p)
    return program_json(p)

@app.post('/v1/merchant/programs/{program_id}/publish')
def publish_program(program_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    p=owned(db,Program,program_id,staff.merchant_id)
    p.status='published';db.commit()
    return program_json(p)


class ProgramEdit(BaseModel):
    title: str | None = Field(default=None,min_length=3,max_length=180)
    description: str | None = Field(default=None,max_length=500)
    stamps_required: int | None = Field(default=None,ge=2,le=30)
    min_purchase_minor: int | None = Field(default=None,ge=0,le=10_000_000)
    reward_minor: int | None = Field(default=None,ge=1,le=10_000_000)

@app.patch('/v1/merchant/programs/{program_id}')
def edit_program(program_id:str,payload:ProgramEdit,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    program=owned(db,Program,program_id,staff.merchant_id)
    changes=payload.model_dump(exclude_unset=True)
    if not changes or any(v is None for v in changes.values()):
        raise HTTPException(422,'Provide at least one valid program change.')
    monetary={'stamps_required','min_purchase_minor','reward_minor'}
    if program.status!='draft' and monetary.intersection(changes):
        raise HTTPException(409,'Active program criteria cannot change. Pause or create a new program instead.')
    for key,value in changes.items():setattr(program,key,value.strip() if isinstance(value,str) else value)
    db.commit()
    return program_json(program)

@app.post('/v1/merchant/programs/{program_id}/pause')
def pause_program(program_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    program=owned(db,Program,program_id,staff.merchant_id)
    if program.status!='published':raise HTTPException(409,'Only published programs may be paused.')
    program.status='paused';db.commit();return program_json(program)

@app.post('/v1/merchant/programs/{program_id}/resume')
def resume_program(program_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    program=owned(db,Program,program_id,staff.merchant_id)
    if program.status!='paused':raise HTTPException(409,'Only paused programs may be resumed.')
    program.status='published';db.commit();return program_json(program)

@app.get('/v1/merchant/claims')
def get_claims(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    claims=db.scalars(select(ReceiptClaim).where(ReceiptClaim.merchant_id==staff.merchant_id).order_by(ReceiptClaim.created_at.desc()).limit(100)).all()
    return [{'id':c.id,'program_id':c.program_id,'consumer_id':c.consumer_id,
             'receipt_id':c.external_receipt_id,'amount_minor':c.amount_minor,'status':c.status} for c in claims]

@app.post('/v1/merchant/claims/{claim_id}/approve')
def approve_claim(claim_id:str,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    c=db.scalar(select(ReceiptClaim).where(ReceiptClaim.id==claim_id,ReceiptClaim.merchant_id==staff.merchant_id).with_for_update())
    if not c:raise HTTPException(404,'Claim not found')
    if c.status!='pending':raise HTTPException(409,'Claim already processed')
    from .pilot_v06 import approval_guard
    approval_guard(db,c,staff)
    p=owned(db,Program,c.program_id,staff.merchant_id)
    membership=db.scalar(select(Membership).where(Membership.consumer_id==c.consumer_id,Membership.program_id==p.id).with_for_update())
    if not membership:raise HTTPException(409,'Membership missing')
    # In a multi-worker production implementation, use SELECT FOR UPDATE and a
    # transaction/advisory lock for this membership before modifying stamps.
    c.status='approved'
    membership.stamps+=1
    awarded=False
    if membership.stamps>=p.stamps_required:
        membership.stamps-=p.stamps_required
        db.add(Reward(merchant_id=staff.merchant_id,program_id=p.id,consumer_id=c.consumer_id,source_claim_id=c.id))
        awarded=True
    db.commit()
    return {'status':'approved','reward_awarded':awarded,'stamps':membership.stamps}

@app.post('/v1/merchant/claims/{claim_id}/reject')
def reject_claim(claim_id:str,body:dict|None=None,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    c=db.scalar(select(ReceiptClaim).where(ReceiptClaim.id==claim_id,ReceiptClaim.merchant_id==staff.merchant_id).with_for_update())
    if not c:raise HTTPException(404,'Claim not found')
    if c.status!='pending':raise HTTPException(409,'Claim already processed')
    from .pilot_v06 import approval_guard
    approval_guard(db,c,staff)
    c.status='rejected'
    from .models_v06 import ReceiptEvidence
    evidence=db.get(ReceiptEvidence,c.id)
    if evidence and body and isinstance(body.get('reason'),str):
        evidence.rejection_reason=body['reason'].strip()[:300]
    db.commit()
    return {'status':'rejected'}

@app.post('/v1/merchant/rewards/{reward_id}/confirm')
def confirm_reward(reward_id:str,payload:ConfirmIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    # This legacy endpoint had no completed sale reference and no audit ledger.
    # Fail closed rather than redeem rewards outside the reconciliation workflow.
    merchant_check(staff)
    raise HTTPException(409,'Legacy confirmation is disabled. Use /v1/merchant/redemptions/confirm with a completed sale reference.')

@app.post('/v1/merchant/campaign-suggestions')
def suggest_campaign(payload:CampaignGoal,staff:Staff=Depends(merchant_actor)):
    # Intentionally a deterministic draft template, NOT an external AI call.
    # Replace behind an interface later, with budget limits, moderation, and approvals.
    goal=payload.goal.strip()
    return {'generator':'template','title':'Local Rewards Week',
            'goal':goal,'message':'Discover our latest loyalty reward on Pruvs. Visit us and earn stamps toward your next reward.',
            'requires_merchant_approval':True}

@app.get('/v1/merchant/campaigns')
def campaigns(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    return [campaign_json(c) for c in db.scalars(select(Campaign).where(Campaign.merchant_id==staff.merchant_id)).all()]

@app.post('/v1/merchant/campaigns',status_code=201)
def create_campaign(payload:CampaignIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    merchant_check(staff)
    c=Campaign(merchant_id=staff.merchant_id,**payload.model_dump(),status='draft',generator='template')
    db.add(c);db.commit();db.refresh(c)
    return campaign_json(c)

@app.get('/v1/discover')
def discover(latitude:float|None=Query(default=None,ge=-90,le=90),longitude:float|None=Query(default=None,ge=-180,le=180),
             radius_km:float=Query(default=10,gt=0,le=50),db:Session=Depends(get_db)):
    if (latitude is None)!=(longitude is None):raise HTTPException(422,'Both coordinates required')
    published=db.scalars(select(Program).where(Program.status=='published')).all()
    results=[]
    for p in published:
        s=db.get(Store,p.store_id)
        if not s or not s.active:continue
        m=db.get(Merchant,p.merchant_id)
        if not m or m.status!='active':continue
        distance=dist_km(latitude,longitude,s.latitude,s.longitude) if latitude is not None else None
        if distance is not None and distance>radius_km:continue
        results.append({'merchant_name':m.name,'store':store_json(s),'program':program_json(p),'distance_km':round(distance,2) if distance is not None else None})
    return sorted(results,key=lambda r:(r['distance_km'] is None,r['distance_km'] or 0))[:100]

@app.post('/v1/customer/programs/{program_id}/join')
def join_program(program_id:str,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    p=db.get(Program,program_id)
    if not p or p.status!='published':raise HTTPException(404,'Program not available')
    existing=db.scalar(select(Membership).where(Membership.consumer_id==consumer_id,Membership.program_id==program_id))
    if existing:return {'membership_id':existing.id,'stamps':existing.stamps,'already_joined':True}
    membership=Membership(consumer_id=consumer_id,program_id=program_id)
    db.add(membership)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        membership=db.scalar(select(Membership).where(Membership.consumer_id==consumer_id,Membership.program_id==program_id))
        if not membership:raise
        return {'membership_id':membership.id,'stamps':membership.stamps,'already_joined':True}
    return {'membership_id':membership.id,'stamps':0,'already_joined':False}


@app.post('/v1/customer/programs/{program_id}/leave')
def leave_program(program_id:str,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    membership=db.scalar(select(Membership).where(Membership.consumer_id==consumer_id,
               Membership.program_id==program_id).with_for_update())
    if not membership:return {'left':True,'already_left':True}
    pending=db.scalar(select(func.count(ReceiptClaim.id)).where(ReceiptClaim.consumer_id==consumer_id,
                      ReceiptClaim.program_id==program_id,ReceiptClaim.status=='pending'))
    pending_rewards=db.scalar(select(func.count(Reward.id)).where(Reward.consumer_id==consumer_id,
                Reward.program_id==program_id,Reward.status.in_(('available','reserved'))))
    if membership.stamps or pending or pending_rewards:
        raise HTTPException(409,'You have stamps, pending receipts or unredeemed rewards. Redeem or resolve them before leaving.')
    db.delete(membership);db.commit()
    return {'left':True,'already_left':False}

@app.post('/v1/customer/claims',status_code=201)
def claim_receipt(payload:ReceiptProofIn,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    p=db.get(Program,payload.program_id)
    if not p or p.status!='published':raise HTTPException(404,'Program not available')
    proof=decode(payload.receipt_proof,settings.pruvs_bridge_secret,'pruvs-core','pruvs-business','receipt_proof')
    if proof.get('sub')!=consumer_id or proof.get('store_id')!=p.store_id or proof.get('currency')!=p.currency:
        raise HTTPException(403,'Receipt proof does not match customer or store')
    amount=proof.get('amount_minor')
    if type(amount) is not int or amount<p.min_purchase_minor or amount<=0:
        raise HTTPException(422,'Receipt is not eligible for this program')
    if not isinstance(proof.get('receipt_id'),str) or not proof['receipt_id']:
        raise HTTPException(422,'Missing receipt reference')
    membership=db.scalar(select(Membership).where(Membership.consumer_id==consumer_id,Membership.program_id==p.id))
    if not membership:raise HTTPException(403,'Join this program first')
    c=ReceiptClaim(merchant_id=p.merchant_id,program_id=p.id,consumer_id=consumer_id,
                   external_receipt_id=proof['receipt_id'],amount_minor=amount,source_system='pruvs',status='pending')
    db.add(c)
    try:db.commit()
    except IntegrityError as e:
        db.rollback();raise HTTPException(409,'Receipt already submitted') from e
    db.refresh(c)
    return {'claim_id':c.id,'status':'pending','message':'Merchant verification required before earning stamps'}

@app.get('/v1/customer/memberships')
def customer_memberships(consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    from .wallet_reads_v068 import membership_rows
    return {'memberships':membership_rows(db,consumer_id)}

@app.get('/v1/customer/wallet')
def wallet(consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    from .wallet_reads_v068 import membership_rows, reward_rows
    return {'memberships':membership_rows(db,consumer_id),
            'rewards':reward_rows(db,consumer_id)}

@app.post('/v1/customer/rewards/{reward_id}/reserve')
def reserve_reward(reward_id:str,consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    r=db.get(Reward,reward_id)
    if not r or r.consumer_id!=consumer_id:raise HTTPException(404,'Reward not found')
    if r.status=='reserved' and aware(r.reserved_until) and aware(r.reserved_until)<utcnow():
        r.status='available';r.redemption_code=None;r.reserved_until=None
    if r.status=='reserved':
        return {'reward_id':r.id,'code':r.redemption_code,'expires_at':r.reserved_until.isoformat()}
    if r.status!='available':raise HTTPException(409,'Reward already used')
    r.status='reserved';r.redemption_code=secrets.token_hex(6).upper();r.reserved_until=utcnow()+timedelta(minutes=10)
    db.commit()
    return {'reward_id':r.id,'code':r.redemption_code,'expires_at':r.reserved_until.isoformat()}

@app.post('/v1/merchant/redemptions/lookup')
def lookup_redemption(payload:ConfirmIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    r=db.scalar(select(Reward).where(Reward.redemption_code==payload.code.upper(),Reward.merchant_id==staff.merchant_id))
    if not r or r.status!='reserved' or not aware(r.reserved_until) or aware(r.reserved_until)<=utcnow():
        raise HTTPException(404,'Active reward code not found')
    p=db.get(Program,r.program_id)
    return {'reward_id':r.id,'program_title':p.title,'reward_minor':p.reward_minor,
            'currency':p.currency,'expires_at':r.reserved_until.isoformat(),
            'message':'Apply discount in fiscal checkout first, then confirm redemption after completed sale.'}

class RedemptionSaleIn(ConfirmIn):
    sale_reference:str=Field(min_length=3,max_length=120)
    sale_amount_minor:int=Field(ge=1,le=10_000_000)

@app.post('/v1/merchant/redemptions/confirm')
def confirm_redemption_code(payload:RedemptionSaleIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    """Mark a reward redeemed only after a completed merchant sale; record the applied discount."""
    merchant_check(staff)
    code=payload.code.upper()
    r=db.scalar(select(Reward).where(Reward.redemption_code==code,
                Reward.merchant_id==staff.merchant_id).with_for_update())
    if not r or r.status!='reserved' or not aware(r.reserved_until) or aware(r.reserved_until)<=utcnow():
        raise HTTPException(409,'Invalid or expired redemption')
    program=owned(db,Program,r.program_id,staff.merchant_id)
    if payload.sale_amount_minor<program.reward_minor:
        raise HTTPException(422,'Sale amount must cover the discount amount.')
    receipt=payload.sale_reference.strip()
    if not receipt:raise HTTPException(422,'Completed sale reference is required.')
    if db.scalar(select(DiscountRedemption.id).where(DiscountRedemption.reward_id==r.id)):
        raise HTTPException(409,'This reward has already been reconciled.')
    record=DiscountRedemption(reward_id=r.id,merchant_id=staff.merchant_id,
        program_id=program.id,source_claim_id=r.source_claim_id,
        consumer_id=r.consumer_id,staff_id=staff.id,sale_reference=receipt,
        sale_amount_minor=payload.sale_amount_minor,discount_minor=program.reward_minor,
        currency=program.currency,verification_source='merchant_attested',created_at=utcnow())
    db.add(record)
    r.status='redeemed';r.redemption_code=None;r.reserved_until=None;r.redeemed_at=utcnow()
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Duplicate or already reconciled redemption') from None
    return {'status':'redeemed','reward_id':r.id,'reconciliation_id':record.id,
            'discount_minor':record.discount_minor,'currency':record.currency,
            'verification_source':'merchant_attested'}

def redemption_json(db,row):
    claim=db.get(ReceiptClaim,row.source_claim_id) if row.source_claim_id else None
    return {'id':row.id,'reward_id':row.reward_id,'program_id':row.program_id,
            'source_receipt_ref':claim.external_receipt_id if claim else None,
            'sale_reference':row.sale_reference,'sale_amount_minor':row.sale_amount_minor,
            'discount_minor':row.discount_minor,'currency':row.currency,
            'verification_source':row.verification_source,'created_at':row.created_at.isoformat()}

@app.get('/v1/merchant/redemptions/reconciliation')
def merchant_reconciliation(limit:int=Query(100,ge=1,le=500),staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    rows=db.scalars(select(DiscountRedemption).where(
        DiscountRedemption.merchant_id==staff.merchant_id)
        .order_by(DiscountRedemption.created_at.desc()).limit(limit)).all()
    return {'rows':[redemption_json(db,r) for r in rows],
            'total_discount_minor':sum(r.discount_minor for r in rows),
            'verification_source':'merchant_attested',
            'notice':'These records document merchant-confirmed discounts, not independently verified POS settlement.'}

@app.get('/v1/merchant/redemptions/reconciliation.csv')
def merchant_reconciliation_csv(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    rows=db.scalars(select(DiscountRedemption).where(
        DiscountRedemption.merchant_id==staff.merchant_id)
        .order_by(DiscountRedemption.created_at.desc()).limit(1000)).all()
    out=StringIO();writer=csv.writer(out)
    writer.writerow(['reconciliation_id','reward_id','program_id','source_receipt_ref','merchant_sale_reference',
                     'sale_amount_minor','discount_minor','currency','verified_by','verified_at','verification_source'])
    for row in rows:
        claim=db.get(ReceiptClaim,row.source_claim_id) if row.source_claim_id else None
        # Prefix untrusted spreadsheet fields to avoid CSV formula injection.
        safe=lambda v: "'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v
        writer.writerow([row.id,row.reward_id,row.program_id,claim.external_receipt_id if claim else '',
                         safe(row.sale_reference),row.sale_amount_minor,row.discount_minor,row.currency,
                         row.staff_id,row.created_at.isoformat(),row.verification_source])
    return Response(out.getvalue(),media_type='text/csv',headers={
        'Content-Disposition':'attachment; filename="pruvs-business-reconciliation.csv"',
        'Cache-Control':'no-store'})

@app.get('/v1/customer/redemptions')
def customer_redemptions(consumer_id:str=Depends(customer_actor),db:Session=Depends(get_db)):
    rows=db.scalars(select(DiscountRedemption).where(
        DiscountRedemption.consumer_id==consumer_id).order_by(
        DiscountRedemption.created_at.desc()).limit(100)).all()
    return [redemption_json(db,row) for row in rows]


# Demo-only bridge simulator. Do not enable outside local development.
# Real Pruvs sessions and receipt ownership must be provided by Pruvs Core
# through a separately reviewed, server-side integration.

def require_local_demo(request:Request):
    cfg=get_settings()
    if cfg.app_env!='development' or not cfg.enable_demo_sandbox:
        raise HTTPException(404,'Demo sandbox is disabled')
    if request.url.hostname not in ('127.0.0.1','localhost','testserver'):
        raise HTTPException(404,'Demo sandbox is local-only')

@app.post('/v1/dev/customer/session')
def dev_customer_session(request:Request, staff:Staff=Depends(merchant_actor)):
    require_local_demo(request)
    from .bridge import issue_session_token
    customer_id='demo-customer-'+staff.merchant_id
    return {'access_token':issue_session_token(customer_id), 'customer_id':customer_id,
            'merchant_id':staff.merchant_id,'demo_only':True}

@app.post('/v1/dev/receipt-proof')
def dev_receipt_proof(payload:DemoReceiptIn,request:Request,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    require_local_demo(request)
    from .bridge import issue_receipt_proof
    p=owned(db,Program,payload.program_id,staff.merchant_id)
    if p.status!='published':raise HTTPException(409,'Program is not published')
    if payload.amount_minor < p.min_purchase_minor:
        raise HTTPException(422,'Demo receipt below qualifying purchase amount')
    demo_receipt_id='sandbox-'+secrets.token_hex(16)
    return {'receipt_id':demo_receipt_id,'receipt_proof':issue_receipt_proof(
                'demo-customer-'+staff.merchant_id,demo_receipt_id,p.store_id,payload.amount_minor,p.currency),
            'warning':'SIMULATED receipt: not a fiscal transaction or Pruvs Core scan'}

from .pilot_v05 import router as pilot_v05_router
app.include_router(pilot_v05_router)

from .pilot_v06 import router as pilot_v06_router
app.include_router(pilot_v06_router)

from .pilot_v12 import router as pilot_v12_router
app.include_router(pilot_v12_router)

# Same-origin merchant UI is opt-in; register only after every API router.
from .ui_host import mount_business_ui
mount_business_ui(app)
