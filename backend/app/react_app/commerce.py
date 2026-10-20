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
from app.models.pruvs_usage import PruvsMeteredUse,PruvsUpgradeRequest
from app.react_app.usage import COSTS,used,metered,credit_balance
from app.react_app.plan_catalog import plan_catalog, credit_costs
from app.react_app.billing import billing_snapshot
from app.react_app.auth import current,admin

router=APIRouter(prefix='/api/v1/commerce',tags=['Pruvs Membership'])
REWARD_CREDITS=5
PLANS={
    'free':{'price_eur':'0.00','ocr_allowance':3,'expense_reports':1},
    'plus':{'price_eur':'2.99','ocr_allowance':50,'expense_reports':10},
    'business':{'price_eur':'5.99','ocr_allowance':75,'expense_reports':25},
}
def canonical_plan(value):
    # Honor old PRO admin assignments as Business without mutating the ledger.
    return 'business' if value == 'pro' else value if value in PLANS else 'free'

def account_plan(db, user_id):
    from app.models.pruvs_billing import PruvsStripeAccount
    row=db.get(DemoSubscription,user_id)
    if not row:
        return 'free'
    if row.status=='admin_assigned':
        return canonical_plan(row.plan)
    if row.status=='stripe_paid':
        stripe_row=db.get(PruvsStripeAccount,user_id)
        if not stripe_row:
            return 'free'
        # Access to a paid period persists after renewal failure, not indefinitely.
        paid_period_valid = (stripe_row.current_period_end is None or
                             stripe_row.current_period_end>datetime.utcnow())
        if paid_period_valid and stripe_row.status in ('active','trialing','past_due'):
            return canonical_plan(stripe_row.plan)
    return 'free'


def membership_on():return os.getenv('PRUVS_MEMBERSHIP_ENABLED','true').lower()=='true'

def credits(db,user_id):
    return int(db.query(func.coalesce(func.sum(CreditEntry.delta),0)).filter(CreditEntry.user_id==user_id).scalar() or 0)

def credit(db,user_id,amount,reason,reference):
    # Unique ledger reference guards repeated webhooks/retries. Never mint from client input.
    if not db.query(CreditEntry.id).filter_by(reference=reference).first():
        db.add(CreditEntry(user_id=user_id,delta=amount,reason=reason,reference=reference))

def new_referral(db,session,user):
    """Attribution attaches automatically to owner invitation, never to a client-supplied owner ID."""
    if not membership_on() or user.id==session.owner_user_id:return
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
    from app.models.pruvs_rewards_policy import PruvsRewardPolicy,PruvsOCRBonusGrant
    policy=db.get(PruvsRewardPolicy,1)
    pc=policy.pc_reward if policy else REWARD_CREDITS
    scans=policy.ocr_bonus if policy else 2
    if pc:credit(db,row.owner_id,pc,'split_referral',f'split-referral:{row.referred_id}')
    if scans and not db.query(PruvsOCRBonusGrant.id).filter_by(reference=f'referral-ocr:{row.referred_id}').first():
        db.add(PruvsOCRBonusGrant(user_id=row.owner_id,amount=scans,reference=f'referral-ocr:{row.referred_id}'))
    db.commit()



def account_snapshot(db,user_id):
    from app.models.external_ocr_usage import ExternalOCRUsage
    row=db.get(DemoSubscription,user_id)
    plan=account_plan(db,user_id)
    begin=datetime.utcnow().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    # This is a historical receipt count, not the new metered AI OCR ledger.
    historic_receipts=(db.query(func.count(Case.id))
       .filter(Case.user_id==user_id,Case.module=='split_bill',Case.created_at>=begin,
               Case.status.notin_(['processing','processing_failed']))
       .scalar() or 0)
    plans=plan_catalog(db)
    billing=billing_snapshot(db,user_id)
    pc_costs=credit_costs(db)
    refs=db.query(Referral).filter_by(owner_id=user_id)
    entries=db.query(CreditEntry).filter_by(user_id=user_id).order_by(CreditEntry.id.desc()).limit(30).all()
    balances={}
    for resource, key in (('ocr','ocr_allowance'),('expense_report','expense_reports')):
        consumed=used(db,user_id,resource)
        allowance=plans[plan][key]
        balances[resource]={'used':consumed,'allowance':allowance,'remaining':max(0,allowance-consumed),
                            'total_completed':metered(db,user_id,resource),
                            'extra_pc':pc_costs[resource]}
    pending=db.query(PruvsUpgradeRequest).filter_by(user_id=user_id,status='pending').order_by(PruvsUpgradeRequest.id.desc()).first()
    return {'plan':plan,'source':'administrator' if row and row.status=='admin_assigned' else 'stripe' if row and row.status=='stripe_paid' and plan!='free' else 'default',
       'plans':plans,'pc_costs':pc_costs,'payment_available':billing['payment_available'],'billing':billing,'credits':credits(db,user_id),
       'purchased_credits':0,'promotional_credits':credits(db,user_id),
       'usage':balances,'month':begin.strftime('%Y-%m'),'billing_timezone':'UTC',
       'upgrade_request':{'id':pending.id,'plan':pending.requested_plan} if pending else None,
       'referrals':{'pending':refs.filter_by(status='pending').count(),'rewarded':refs.filter_by(status='rewarded').count()},
       'ocr':{'completed_receipts_this_month':int(historic_receipts),'plan_allowance':plans[plan]['ocr_allowance'],
              'note':'Historical receipt activity; metered usage applies to new operations from v7.1.12.'},
       'reward_policy':reward_policy_data(db), 'bonus_ocr_remaining':bonus_ocr_remaining(db,user_id),
       'storage':{'mode':'local' if plan=='free' else 'cloud','description':'Only on this device. No cloud backup.' if plan=='free' else 'Private cloud backup and local offline copy.'},
       'credit_entries':[{'delta':e.delta,'reason':e.reason,'at':e.created_at.isoformat()} for e in entries]}

def reward_policy_data(db):
    from app.models.pruvs_rewards_policy import PruvsRewardPolicy
    row=db.get(PruvsRewardPolicy,1)
    return {'pc_reward':row.pc_reward if row else 5,'ocr_bonus':row.ocr_bonus if row else 2,
            'version':row.version if row else 0}

def bonus_ocr_remaining(db,user_id):
    from app.react_app.usage import bonus_remaining
    return bonus_remaining(db,user_id)

@router.get('/admin/referral-rewards')
def admin_referral_rewards(identity=Depends(admin),db=Depends(get_db)):
    return reward_policy_data(db)

@router.put('/admin/referral-rewards')
def admin_update_referral_rewards(body:dict,identity=Depends(admin),db=Depends(get_db)):
    from app.models.pruvs_rewards_policy import PruvsRewardPolicy
    from app.react_app.plan_catalog import _count
    row=db.query(PruvsRewardPolicy).filter_by(id=1).with_for_update().first()
    before=reward_policy_data(db)
    if int(body.get('version',-1))!=before['version']:
        raise HTTPException(409,'Referral reward policy changed. Refresh and retry.')
    pc=_count(body.get('pc_reward'), 'Referral PC', 1000)
    scans=_count(body.get('ocr_bonus'), 'Referral OCR bonus', 100)
    if not row:
        row=PruvsRewardPolicy(id=1)
        db.add(row)
    row.pc_reward=pc;row.ocr_bonus=scans;row.version=before['version']+1
    row.updated_by=identity[0].id;row.updated_at=datetime.utcnow()
    db.commit()
    return reward_policy_data(db)

@router.put('/admin/users/{uid}/credits')
def admin_edit_credits(uid:int,body:dict,identity=Depends(admin),db=Depends(get_db)):
    from app.react_app.usage import lock_user
    from app.react_app.plan_catalog import _count
    target=db.query(User).filter_by(id=uid).with_for_update().first()
    if not target or target.status=='deleted':raise HTTPException(404,'User not found.')
    new_balance=_count(body.get('balance'), 'PC balance', 1_000_000)
    lock_user(db,uid)
    old=credits(db,uid)
    expected=_count(body.get('expected_balance'), 'Expected PC balance', 1_000_000)
    if old!=expected:raise HTTPException(409,'Credit balance changed. Refresh the user before editing.')
    delta=new_balance-old
    if delta:
        credit(db,uid,delta,'admin_balance_adjustment',f'admin-pc:{uid}:{secrets.token_hex(16)}')
        db.commit()
    return {'user_id':uid,'credits':credits(db,uid),'delta':delta}

@router.get('/status')
def status(identity=Depends(current),db=Depends(get_db)):
    return account_snapshot(db,identity[0].id)

@router.put('/admin/users/{uid}/subscription')
def assign_subscription(uid:int,body:dict,identity=Depends(admin),db=Depends(get_db)):
    plan=str(body.get('plan','')).strip().lower()
    if plan not in PLANS:raise HTTPException(422,'Choose free, plus or business.')
    from app.models.pruvs_billing import PruvsStripeAccount
    subscribed=db.get(PruvsStripeAccount,uid)
    if subscribed and subscribed.subscription_id and subscribed.status not in ('canceled','none','incomplete_expired'):
        raise HTTPException(409,'Cancel the Stripe subscription before assigning a complimentary plan.')
    target=db.query(User).filter_by(id=uid).with_for_update().first()
    if not target or target.status=='deleted':raise HTTPException(404,'Account not found.')
    row=db.get(DemoSubscription,uid)
    if row is None:row=DemoSubscription(user_id=uid);db.add(row)
    row.plan=plan;row.status='admin_assigned';row.activated_at=datetime.utcnow();row.expires_at=None
    # Plan changes are never the source of Pruvs credit grants.
    for req in db.query(PruvsUpgradeRequest).filter_by(user_id=uid,status='pending').all():
        req.status='approved' if req.requested_plan==plan else 'superseded'
        req.reviewed_at=datetime.utcnow();req.reviewed_by=identity[0].id
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


@router.post('/upgrade-request')
def request_upgrade(body:dict,identity=Depends(current),db=Depends(get_db)):
    wanted=str(body.get('plan','')).strip().lower()
    if wanted not in ('plus','business'):
        raise HTTPException(422,'Select Plus or Business.')
    uid=identity[0].id
    if account_plan(db,uid)==wanted:
        raise HTTPException(409,'Your account is already on that plan.')
    existing=db.query(PruvsUpgradeRequest).filter_by(user_id=uid,status='pending').first()
    if existing:
        existing.requested_plan=wanted
        existing.requested_at=datetime.utcnow()
    else:
        existing=PruvsUpgradeRequest(user_id=uid,requested_plan=wanted,status='pending')
        db.add(existing)
    db.commit()
    return {'ok':True,'status':'pending','plan':wanted,'payment_charged':False,
            'message':'Your request has been submitted to Pruvs administration. No payment was collected.'}

@router.get('/admin/upgrade-requests')
def pending_upgrades(identity=Depends(admin),db=Depends(get_db)):
    pending=db.query(PruvsUpgradeRequest).filter_by(status='pending').order_by(PruvsUpgradeRequest.requested_at.desc()).limit(100).all()
    rows=[]
    for r in pending:
        user=db.get(User,r.user_id)
        rows.append({'id':r.id,'user_id':r.user_id,'name':user.name if user else 'Unknown',
                     'email':user.email if user else '', 'requested_plan':r.requested_plan,
                     'current_plan':account_plan(db,r.user_id),
                     'requested_at':r.requested_at.isoformat()})
    return rows

@router.post('/admin/upgrade-requests/{req_id}/decline')
def decline_upgrade(req_id:int,identity=Depends(admin),db=Depends(get_db)):
    row=db.query(PruvsUpgradeRequest).filter_by(id=req_id,status='pending').with_for_update().first()
    if not row:raise HTTPException(404,'Pending request not found.')
    row.status='declined';row.reviewed_by=identity[0].id;row.reviewed_at=datetime.utcnow()
    db.commit()
    return {'ok':True}

@router.post('/referrals/reconcile')
def reconcile_referrals(identity=Depends(current),db=Depends(get_db)):
    """Retry eligible historic pending referrals from persisted item assignments."""
    owner_id=identity[0].id
    count=0
    pending=db.query(Referral).filter_by(owner_id=owner_id,status='pending').limit(100).all()
    for r in pending:
        u=db.get(User,r.referred_id)
        s=db.get(SplitBillSession,r.session_id)
        if not u or not s or s.owner_user_id!=owner_id or not u.is_email_verified:
            continue
        p=db.query(SplitBillParticipant).filter_by(session_id=s.id,user_id=u.id,status='joined').first()
        if not p:
            continue
        assignment=db.query(SplitBillItemAssignment.id).filter(
            SplitBillItemAssignment.participant_id==p.id,SplitBillItemAssignment.amount>0).first()
        if not assignment:
            continue
        qualify_referral(db,s,u,{'persisted_assignment':1})
        db.refresh(r)
        if r.status=='rewarded':count+=1
    return {'ok':True,'newly_rewarded':count,'status':account_snapshot(db,owner_id)}
