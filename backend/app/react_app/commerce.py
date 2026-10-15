"""Pruvs membership and non-transferable app credits. Card purchases are disabled."""
import io
import os
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from app.models.case import Case
from app.models.user import User
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.pruvs_commerce import DemoSubscription,CreditEntry,Referral
from app.react_app.auth import current,admin

router=APIRouter(prefix='/api/v1/commerce',tags=['Pruvs Membership'])
REWARD_CREDITS=20
PLANS={'free':{'monthly_demo_price_eur':'0.00','ocr_allowance':5},'plus':{'monthly_demo_price_eur':'2.99','ocr_allowance':100},'pro':{'monthly_demo_price_eur':'5.99','ocr_allowance':300}}

def membership_on():return os.getenv('PRUVS_MEMBERSHIP_ENABLED','true').lower()=='true'

def credits(db,user_id):
    return int(db.query(func.coalesce(func.sum(CreditEntry.delta),0)).filter(CreditEntry.user_id==user_id).scalar() or 0)

def credit(db,user_id,amount,reason,reference):
    # Unique ledger reference guards repeated webhooks/retries. Never mint from client input.
    if not db.query(CreditEntry.id).filter_by(reference=reference).first():
        db.add(CreditEntry(user_id=user_id,delta=amount,reason=reason,reference=reference))

def new_referral(db,session,user):
    """Attribution attaches automatically to owner invitation, never to a client-supplied owner ID."""
    if not membership_on() or user.id==session.owner_user_id or not user.is_email_verified:return
    created=getattr(user,'created_at',None)
    bill_created=getattr(session,'created_at',None)
    if not created or not bill_created or created < bill_created:return
    if db.query(Referral.id).filter_by(referred_id=user.id).first():return
    db.add(Referral(owner_id=session.owner_user_id,referred_id=user.id,session_id=session.id,status='pending'))
    try:db.commit()
    except IntegrityError:db.rollback() # Another concurrent join already attributed this user.

def qualify_referral(db,session,user,quantities):
    """Only a newly registered verified account selecting a real item qualifies."""
    if not membership_on() or not user.is_email_verified or not any(float(v)>0 for v in quantities.values()):return
    row=db.query(Referral).filter_by(referred_id=user.id,session_id=session.id,status='pending').with_for_update().first()
    if not row:return
    # Eligibility confirmed from persisted assignment, not merely the request payload.
    participant=db.query(SplitBillParticipant).filter_by(session_id=session.id,user_id=user.id,status='joined').first()
    if not participant:return
    assignment=db.query(SplitBillItemAssignment.id).filter(SplitBillItemAssignment.participant_id==participant.id,SplitBillItemAssignment.amount>0).first()
    if not assignment:return
    # Cap referral rewards to 10 per inviter per UTC day in demo mode.
    today=datetime.utcnow().date()
    today_count=db.query(Referral).filter(Referral.owner_id==row.owner_id,Referral.status=='rewarded',Referral.rewarded_at>=datetime.combine(today,datetime.min.time())).count()
    if today_count>=10:return
    row.status='rewarded';row.rewarded_at=datetime.utcnow()
    credit(db,row.owner_id,REWARD_CREDITS,'split_referral',f'split-referral:{row.referred_id}')
    db.commit()



def account_snapshot(db,user_id):
    from app.models.external_ocr_usage import ExternalOCRUsage
    from app.models.case import Case
    from sqlalchemy import distinct
    row=db.get(DemoSubscription,user_id)
    # Older sandbox plan selections do not become live entitlements automatically.
    plan=row.plan if row and row.status=='admin_assigned' and row.plan in PLANS else 'free'
    start=datetime.utcnow().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    # The React capture path uses direct Azure OCR, which does not necessarily
    # generate ExternalOCRUsage rows. Count successfully processed user receipts
    # instead of relying exclusively on the external-provider router log.
    ocr_count=(db.query(func.count(Case.id))
       .filter(Case.user_id==user_id,Case.module=='split_bill',Case.created_at>=start,
               Case.status.notin_(['processing','processing_failed']))
       .scalar() or 0)
    refs=db.query(Referral).filter_by(owner_id=user_id)
    entries=db.query(CreditEntry).filter_by(user_id=user_id).order_by(CreditEntry.id.desc()).limit(20).all()
    return {'plan':plan,'source':'administrator' if row and row.status=='admin_assigned' else 'default',
       'plans':PLANS,'payment_available':False,'credits':credits(db,user_id),
       'purchased_credits':0,'promotional_credits':credits(db,user_id),
       'referrals':{'pending':refs.filter_by(status='pending').count(),'rewarded':refs.filter_by(status='rewarded').count()},
       'ocr':{'completed_receipts_this_month':int(ocr_count),'plan_allowance':PLANS[plan]['ocr_allowance'],
              'note':'Processed receipt records this month; not a provider invoice or enforced usage cap.'},
       'credit_entries':[{'delta':e.delta,'reason':e.reason,'at':e.created_at.isoformat()} for e in entries]}

@router.get('/status')
def status(identity=Depends(current),db=Depends(get_db)):
    return account_snapshot(db,identity[0].id)

@router.put('/admin/users/{uid}/subscription')
def assign_subscription(uid:int,body:dict,identity=Depends(admin),db=Depends(get_db)):
    plan=str(body.get('plan','')).strip().lower()
    if plan not in PLANS:raise HTTPException(422,'Choose free, plus or pro.')
    target=db.query(User).filter_by(id=uid).with_for_update().first()
    if not target or target.status=='deleted':raise HTTPException(404,'Account not found.')
    row=db.get(DemoSubscription,uid)
    if row is None:row=DemoSubscription(user_id=uid);db.add(row)
    row.plan=plan;row.status='admin_assigned';row.activated_at=datetime.utcnow();row.expires_at=None
    # Plan changes are never the source of Pruvs credit grants.
    db.commit()
    return {'ok':True,'user_id':uid,'plan':plan,'payment_charged':False,'assigned_by':identity[0].id}

@router.get('/admin/users/{uid}/membership')
def admin_membership(uid:int,identity=Depends(admin),db=Depends(get_db)):
    target=db.get(User,uid)
    if not target:raise HTTPException(404,'Account not found.')
    return account_snapshot(db,uid)

# No public subscription checkout or spending endpoint until an actual payment
# provider, entitlement enforcement, and credit accounting policy are approved.
# Merchant loyalty APIs have been retired; historical database rows are retained.
