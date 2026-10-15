"""Pruvs demo commerce endpoints. NO card entry, payment capture or auto POS matching."""
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
from app.models.pruvs_commerce import DemoSubscription,CreditEntry,Referral,Merchant,Campaign,ReceiptMark,RewardClaim,RewardVoucher
from app.react_app.auth import current,admin

router=APIRouter(prefix='/api/v1/commerce',tags=['Pruvs Commerce Demo'])
REWARD_CREDITS=20
PLANS={'free':{'monthly_demo_price_eur':'0.00','ocr_allowance':5},'plus':{'monthly_demo_price_eur':'2.99','ocr_allowance':100},'pro':{'monthly_demo_price_eur':'5.99','ocr_allowance':300}}

def demo_on():return os.getenv('PRUVS_COMMERCE_DEMO_ENABLED','false').lower()=='true'
def require_demo():
    if not demo_on():raise HTTPException(503,'Commerce demo is disabled. Set PRUVS_COMMERCE_DEMO_ENABLED=true for a controlled test.')

def credits(db,user_id):
    return int(db.query(func.coalesce(func.sum(CreditEntry.delta),0)).filter(CreditEntry.user_id==user_id).scalar() or 0)

def credit(db,user_id,amount,reason,reference):
    # Unique ledger reference guards repeated webhooks/retries. Never mint from client input.
    if not db.query(CreditEntry.id).filter_by(reference=reference).first():
        db.add(CreditEntry(user_id=user_id,delta=amount,reason=reason,reference=reference))

def new_referral(db,session,user):
    """Attribution attaches automatically to owner invitation, never to a client-supplied owner ID."""
    if not demo_on() or user.id==session.owner_user_id or not user.is_email_verified:return
    created=getattr(user,'created_at',None)
    bill_created=getattr(session,'created_at',None)
    if not created or not bill_created or created < bill_created:return
    if db.query(Referral.id).filter_by(referred_id=user.id).first():return
    db.add(Referral(owner_id=session.owner_user_id,referred_id=user.id,session_id=session.id,status='pending'))
    try:db.commit()
    except IntegrityError:db.rollback() # Another concurrent join already attributed this user.

def qualify_referral(db,session,user,quantities):
    """Only a newly registered verified account selecting a real item qualifies."""
    if not demo_on() or not user.is_email_verified or not any(float(v)>0 for v in quantities.values()):return
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

@router.get('/status')
def status(identity=Depends(current),db=Depends(get_db)):
    u=identity[0];sub=db.get(DemoSubscription,u.id)
    referrals=db.query(Referral).filter_by(owner_id=u.id)
    return {'demo_enabled':demo_on(),'mode':'DEMO – NO REAL CHARGES','plan':sub.plan if sub else 'free',
      'plans':PLANS,'demo_subscription':bool(sub),'credits':credits(db,u.id),
      'referrals':{'pending':referrals.filter_by(status='pending').count(),'rewarded':referrals.filter_by(status='rewarded').count()},
      'credit_entries':[{'delta':e.delta,'reason':e.reason,'at':e.created_at.isoformat()} for e in db.query(CreditEntry).filter_by(user_id=u.id).order_by(CreditEntry.id.desc()).limit(20).all()]}

@router.post('/demo-checkout')
def demo_checkout(body:dict,identity=Depends(current),db=Depends(get_db)):
    require_demo()
    plan=str(body.get('plan','')).lower()
    if plan not in ('plus','pro','free'):raise HTTPException(422,'Unknown plan')
    user=identity[0]
    row=db.get(DemoSubscription,user.id)
    if row is None:row=DemoSubscription(user_id=user.id);db.add(row)
    row.plan=plan;row.status='demo';row.activated_at=datetime.utcnow();row.expires_at=datetime.utcnow()+timedelta(days=30)
    db.commit()
    return {'ok':True,'demo':True,'plan':plan,'charged':False,'message':'Simulated checkout only. No card, invoice or bank transaction.'}

@router.post('/demo-spend')
def demo_spend(body:dict,identity=Depends(current),db=Depends(get_db)):
    require_demo()
    action=str(body.get('action',''))
    costs={'ai_scan_test':2,'export_test':5}
    if action not in costs:raise HTTPException(422,'Unknown demo action')
    user=identity[0];cost=costs[action]
    # Lock user row across concurrent requests (PostgreSQL); no real OCR/export is performed.
    db.query(User).filter_by(id=user.id).with_for_update().first()
    if credits(db,user.id)<cost:raise HTTPException(409,'Not enough promotional Pruvs Credits')
    credit(db,user.id,-cost,action,'demo-spend:'+secrets.token_hex(18));db.commit()
    return {'ok':True,'cost':cost,'balance':credits(db,user.id),'demo':True}

def public_campaign(db,c):
    m=db.get(Merchant,c.merchant_id)
    return {'id':c.id,'code':c.code,'merchant_name':m.name,'merchant_id':m.id,'title':c.title,
            'threshold_minor':c.threshold_minor,'required_receipts':c.required_receipts,
            'voucher_minor':c.voucher_minor,'currency':c.currency,'demo_only':c.demo_only,'active':c.active}

@router.get('/campaigns')
def campaigns(identity=Depends(current),db=Depends(get_db)):
    return [public_campaign(db,c) for c in db.query(Campaign).filter_by(active=True).order_by(Campaign.id.desc()).limit(100).all()]

@router.get('/campaigns/{code}')
def campaign(code:str,db=Depends(get_db)):
    c=db.query(Campaign).filter_by(code=code,active=True).first()
    if not c:raise HTTPException(404,'Campaign unavailable')
    return public_campaign(db,c)

@router.get('/receipts/{case_id}')
def receipt_campaign(case_id:int,identity=Depends(current),db=Depends(get_db)):
    u=identity[0];case=db.get(Case,case_id)
    if not case or (case.user_id!=u.id and not u.is_admin):raise HTTPException(404,'Receipt unavailable')
    rows=[]
    for mark in db.query(ReceiptMark).filter_by(case_id=case_id).all():
        camp=db.get(Campaign,mark.campaign_id)
        if camp:
            claim=db.query(RewardClaim).filter_by(user_id=case.user_id,case_id=case_id,campaign_id=camp.id).first()
            rows.append({'campaign':public_campaign(db,camp),'marked':True,'claim_status':claim.status if claim else None})
    return {'case_id':case_id,'campaign_marks':rows,'original_unchanged':True,'demo_watermark':True}

@router.post('/receipts/{case_id}/claim')
def claim(case_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    require_demo()
    u=identity[0];case=db.get(Case,case_id)
    if not case or case.user_id!=u.id:raise HTTPException(404,'Receipt unavailable')
    code=str(body.get('campaign_code',''))[:40]
    camp=db.query(Campaign).filter_by(code=code,active=True).first()
    if not camp:raise HTTPException(404,'Campaign unavailable')
    mark=db.query(ReceiptMark).filter_by(case_id=case_id,campaign_id=camp.id).first()
    if not mark:raise HTTPException(409,'Admin must apply the campaign demo watermark before a claim can be submitted.')
    from app.services import standalone_app_service as receiptservice
    record=receiptservice.get_receipt_view(db,case_id,user_id=u.id,ensure_translations=False)
    if (str(record.get('currency') or '').upper()!=camp.currency or round(float(record.get('receipt_total') or 0)*100)<camp.threshold_minor):
        raise HTTPException(409,'Receipt currency or amount is not eligible for this campaign.')
    prev=db.query(RewardClaim).filter_by(case_id=case_id,campaign_id=camp.id).first()
    if prev:return {'claim_id':prev.id,'status':prev.status,'demo':True}
    row=RewardClaim(user_id=u.id,case_id=case_id,campaign_id=camp.id)
    db.add(row);db.commit();db.refresh(row)
    return {'claim_id':row.id,'status':'pending','demo':True,'note':'Requires manual administrator verification; OCR alone does not prove purchase.'}

@router.get('/my-rewards')
def my_rewards(identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id
    claims=db.query(RewardClaim).filter_by(user_id=uid).order_by(RewardClaim.id.desc()).limit(100).all()
    vouchers=db.query(RewardVoucher).filter_by(user_id=uid).order_by(RewardVoucher.id.desc()).all()
    return {'claims':[{'id':x.id,'campaign':public_campaign(db,db.get(Campaign,x.campaign_id)),'status':x.status,'case_id':x.case_id} for x in claims],
       'vouchers':[{'code':v.code,'campaign':public_campaign(db,db.get(Campaign,v.campaign_id)),'status':v.status,'demo':True} for v in vouchers]}

@router.get('/admin/dashboard')
def admin_dashboard(identity=Depends(admin),db=Depends(get_db)):
    return {'merchants':[{'id':m.id,'name':m.name,'tax_id':m.tax_id} for m in db.query(Merchant).order_by(Merchant.id.desc()).limit(100).all()],
      'campaigns':[public_campaign(db,c) for c in db.query(Campaign).order_by(Campaign.id.desc()).limit(100).all()],
      'claims':[{'id':q.id,'case_id':q.case_id,'user_id':q.user_id,'status':q.status,'campaign_id':q.campaign_id} for q in db.query(RewardClaim).order_by(RewardClaim.id.desc()).limit(100).all()]}

@router.post('/admin/merchants')
def create_merchant(body:dict,identity=Depends(admin),db=Depends(get_db)):
    require_demo()
    name=str(body.get('name') or '').strip()[:160]
    if len(name)<3:raise HTTPException(422,'Merchant name must be at least 3 characters.')
    row=Merchant(name=name,tax_id=str(body.get('tax_id') or '')[:40]);db.add(row);db.commit();db.refresh(row)
    return {'id':row.id,'name':row.name}

@router.post('/admin/campaigns')
def create_campaign(body:dict,identity=Depends(admin),db=Depends(get_db)):
    require_demo()
    m=db.get(Merchant,int(body.get('merchant_id',0)))
    if not m:raise HTTPException(404,'Merchant unavailable.')
    title=str(body.get('title') or '').strip()[:180]
    threshold=int(body.get('threshold_minor',5000));required=int(body.get('required_receipts',3));voucher=int(body.get('voucher_minor',2000));currency=str(body.get('currency','RON')).upper()
    if not title or not 1<=required<=20 or not 0<=threshold<=100000000 or not 0<voucher<=100000000 or currency not in ('RON','EUR','USD'):
        raise HTTPException(422,'Invalid campaign configuration.')
    row=Campaign(merchant_id=m.id,code='PRV'+secrets.token_hex(5).upper(),title=title,threshold_minor=threshold,required_receipts=required,voucher_minor=voucher,currency=currency)
    db.add(row);db.commit();db.refresh(row)
    return public_campaign(db,row)

@router.post('/admin/marks')
def mark_receipt(body:dict,identity=Depends(admin),db=Depends(get_db)):
    require_demo()
    case_id=int(body.get('case_id',0));campaign_id=int(body.get('campaign_id',0))
    if not db.get(Case,case_id):raise HTTPException(404,'Receipt unavailable')
    if not db.get(Campaign,campaign_id):raise HTTPException(404,'Campaign unavailable')
    existing=db.query(ReceiptMark).filter_by(case_id=case_id,campaign_id=campaign_id).first()
    if existing:return {'ok':True,'case_id':case_id,'already_marked':True}
    db.add(ReceiptMark(case_id=case_id,campaign_id=campaign_id,admin_id=identity[0].id));db.commit()
    return {'ok':True,'case_id':case_id,'already_marked':False}

@router.post('/admin/claims/{claim_id}/review')
def review_claim(claim_id:int,body:dict,identity=Depends(admin),db=Depends(get_db)):
    require_demo()
    status=str(body.get('status',''))
    if status not in ('verified','rejected'):raise HTTPException(422,'Choose verified or rejected')
    row=db.query(RewardClaim).filter_by(id=claim_id).with_for_update().first()
    if not row:raise HTTPException(404,'Claim unavailable')
    if row.status!='pending':raise HTTPException(409,'Claim already reviewed')
    row.status=status;row.reviewed_at=datetime.utcnow();row.reviewed_by=identity[0].id
    if status=='verified':
        camp=db.get(Campaign,row.campaign_id)
        approved=db.query(RewardClaim).filter_by(user_id=row.user_id,campaign_id=camp.id,status='verified').count()
        if approved >= camp.required_receipts and not db.query(RewardVoucher.id).filter_by(user_id=row.user_id,campaign_id=camp.id).first():
            db.add(RewardVoucher(user_id=row.user_id,campaign_id=camp.id,code='PV-'+secrets.token_hex(6).upper()))
    db.commit()
    return {'ok':True,'status':status,'demo':True}

@router.get('/campaigns/{code}/qr.png')
def campaign_qr(code:str,db=Depends(get_db)):
    camp=db.query(Campaign).filter_by(code=code,active=True).first()
    if not camp:raise HTTPException(404,'Campaign unavailable')
    try:
        import qrcode
        from PIL import Image,ImageDraw,ImageFont
    except ImportError:raise HTTPException(503,'QR generator dependency missing: install qrcode[pil].')
    public_url=os.getenv('PUBLIC_BASE_URL','https://pruvs.io').rstrip('/')+'/rewards/merchant/'+camp.code
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,box_size=12,border=4)
    qr.add_data(public_url);qr.make(fit=True);img=qr.make_image(fill_color='black',back_color='white').convert('RGB')
    # Logo is decorative only, not part of receipt or verification proof.
    side=img.width;logo_path=os.path.join(os.path.dirname(__file__),'..','static','pruvs-logo.png')
    if os.path.isfile(logo_path):
        logo=Image.open(logo_path).convert('RGBA');max_size=int(side*.15);logo.thumbnail((max_size,max_size))
        ImageDraw.Draw(img).rounded_rectangle((side//2-max_size//2-8,side//2-max_size//2-8,side//2+max_size//2+8,side//2+max_size//2+8),radius=12,fill='white')
        img.paste(logo,((side-logo.width)//2,(side-logo.height)//2),logo)
    else:
        draw=ImageDraw.Draw(img);draw.rounded_rectangle((side//2-22,side//2-22,side//2+22,side//2+22),radius=8,fill='white');draw.text((side//2-7,side//2-12),'P',fill='black')
    buff=io.BytesIO();img.save(buff,format='PNG')
    return Response(buff.getvalue(),media_type='image/png',headers={'Cache-Control':'public,max-age=300','Content-Disposition':f'inline; filename="pruvs-campaign-{camp.code}.png"'})


@router.get('/receipts/{case_id}/preview')
def receipt_preview(case_id:int,identity=Depends(current),db=Depends(get_db)):
    """Read-only ORIGINAL preview, with no watermark baked into document bytes."""
    u=identity[0];case=db.get(Case,case_id)
    if not case or (case.user_id!=u.id and not u.is_admin):raise HTTPException(404,'Receipt unavailable')
    from app.models.document import Document
    from app.services.document_service import resolve_document_path
    doc=db.query(Document).filter_by(case_id=case_id).order_by(Document.id.desc()).first()
    path=resolve_document_path(doc)
    if not path:raise HTTPException(404,'Receipt original not available')
    return FileResponse(path,media_type=doc.mime_type or 'application/octet-stream',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; sandbox"})
