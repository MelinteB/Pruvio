import base64
import csv
import io
import json
import math
import os
import secrets
from datetime import datetime,timedelta
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request,Response,UploadFile,File,Query
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from sqlalchemy import String,cast,or_
from app.db.database import get_db
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_fingerprint import ReceiptFingerprint
from app.services.document_service import MAX_FILE_SIZE_BYTES, resolve_document_path, restore_missing_original
from app.services.receipt_duplicates import fingerprint, same_image
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.react_session import ReactChallenge
from app.models.push_notification import PushEvent
from app.services import account_service as accounts,onboarding_otp_service as onboarding,passkey_service as passkeys
from app.services import standalone_app_service as receipts
from app.react_app import bill_service as bills
from app.services import admin_dashboard_service as dashboard
from app.services.auth_service import authenticate_with_password
from app.services.username_service import update_username
from app.react_app.auth import current,admin,profile,issue,revoke,revoke_user,limit,digest,secure,COOKIE,CSRF_COOKIE
router=APIRouter(prefix='/api/v1')

class Payload(BaseModel):
    data:dict=Field(default_factory=dict)

@router.get('/config')
def config():
    from app.services.receipt_currency_service import CURRENCY_OPTIONS
    return {'version':'7.1.10','passkeys':passkeys.passkeys_enabled(),'currencies':CURRENCY_OPTIONS,
            'support_email':os.getenv('PRUVIO_SUPPORT_EMAIL','')}

@router.get('/me')
def me(request:Request,identity=Depends(current)):
    return {'user':profile(identity[0]),'csrf':request.cookies.get(CSRF_COOKIE,'')}

@router.get('/fx/quote')
def fx_quote(base:str,target:str,amount:str,provider:str='bnr',manual_rate:str|None=None,identity=Depends(current)):
    from app.services.reference_fx import reference_quote
    return reference_quote(amount,base,target,provider,manual_rate)

@router.post('/auth/login')
def login(body:dict,request:Request,response:Response,db=Depends(get_db)):
    limit(db,request,'login')
    user=authenticate_with_password(db,str(body.get('identifier',''))[:255],str(body.get('password',''))[:1024])
    return issue(db,user,request,response)

@router.post('/auth/logout')
def logout(response:Response,identity=Depends(current),db=Depends(get_db)):
    revoke(db,identity[1].token_hash);db.commit()
    response.delete_cookie(COOKIE,path='/');response.delete_cookie(CSRF_COOKIE,path='/')
    return {'ok':True}

@router.post('/auth/register')
def register(body:dict,request:Request,db=Depends(get_db)):
    limit(db,request,'registration',10)
    if not body.get('password'):raise ValueError('Password is required.')
    if body.get('notifications_opt_in') is not True or body.get('notification_permission') != 'granted':
        raise ValueError('Allow device notifications before requesting the email code.')
    result=onboarding.start_registration(db,phone_number=body.get('phone_number',''),display_name=body.get('name',''),
        email=body.get('email',''),username=body.get('username',''),password=body.get('password'),
        accepted_terms=body.get('accepted_terms') is True,accepted_privacy=body.get('accepted_privacy') is True,
        marketing_opt_in=body.get('marketing_opt_in') is True)
    result['user'].notifications_opt_in=True
    db.commit()
    return {'challenge_id':result['challenge_id'],'delivery':result['email_delivery'],'email':result['user'].email}

@router.post('/auth/register/resend')
def resend(body:dict,request:Request,db=Depends(get_db)):
    limit(db,request,'registration',10)
    user=onboarding.find_user_by_email(db,str(body.get('email','')))
    if not user or user.status!='pending_join':raise ValueError('No pending registration found.')
    result=onboarding.resend_registration_code(db,user)
    return {k:v for k,v in result.items() if k not in ('user','debug_otp','debug_email_otp')}

@router.post('/auth/register/verify')
def verify_registration(body:dict,request:Request,response:Response,db=Depends(get_db)):
    limit(db,request,'verify',30)
    user=onboarding.verify_registration_email(db,body.get('email',''),body.get('code',''),challenge_id=body.get('challenge_id',''))
    return issue(db,user,request,response)

@router.post('/auth/reset')
def reset(body:dict,request:Request,db=Depends(get_db)):
    limit(db,request,'reset',10)
    result=accounts.request_password_reset(db,body.get('email',''))
    return {k:v for k,v in result.items() if k!='debug_otp'}

@router.post('/auth/reset/confirm')
def reset_confirm(body:dict,request:Request,db=Depends(get_db)):
    limit(db,request,'verify',30)
    user=accounts.confirm_password_reset(db,body.get('email',''),body.get('code',''),body.get('password',''),challenge_id=body.get('challenge_id',''))
    revoke_user(db,user.id);db.commit();return {'ok':True}

@router.post('/auth/passkey/options')
def passkey_login_options(request:Request,response:Response,db=Depends(get_db)):
    limit(db,request,'passkey',30)
    challenge,options=passkeys.begin_passkey_authentication()
    return store_challenge(db,challenge,options,'login',None,response)

def store_challenge(db,challenge,options,purpose,user_id,response):
    binding=secrets.token_urlsafe(32);key=secrets.token_urlsafe(24)
    db.add(ReactChallenge(id=key,purpose=purpose,user_id=user_id,challenge=base64.b64encode(challenge).decode(),
        binding_hash=digest(binding),expires_at=datetime.utcnow()+timedelta(minutes=5)));db.commit()
    response.set_cookie('pruvs_webauthn',binding,httponly=True,secure=secure(),samesite='strict',max_age=300,path='/')
    return {'challenge_id':key,'options':json.loads(options)}

def consume(db,request,key,purpose,uid=None):
    row=db.query(ReactChallenge).filter_by(id=key).with_for_update().first()
    if not row or row.purpose!=purpose or row.user_id!=uid or row.expires_at<datetime.utcnow() or not secrets.compare_digest(row.binding_hash,digest(request.cookies.get('pruvs_webauthn',''))):
        raise ValueError('Passkey challenge expired. Please try again.')
    challenge=base64.b64decode(row.challenge);db.delete(row);db.commit();return challenge

@router.post('/auth/passkey/verify')
def passkey_login_verify(body:dict,request:Request,response:Response,db=Depends(get_db)):
    limit(db,request,'verify',30)
    user=passkeys.complete_passkey_authentication(db,challenge=consume(db,request,body.get('challenge_id'),'login'),browser_credential=body.get('credential',{}))
    return issue(db,user,request,response)

@router.get('/account/passkeys')
def list_passkeys(identity=Depends(current),db=Depends(get_db)):
    return [{'id':p.id,'name':p.device_name,'created_at':p.created_at,'last_used_at':p.last_used_at} for p in passkeys.list_user_passkeys(db,identity[0].id)]

@router.post('/account/passkeys/options')
def passkey_add_options(response:Response,identity=Depends(current),db=Depends(get_db)):
    challenge,options=passkeys.begin_passkey_registration(db,identity[0]);return store_challenge(db,challenge,options,'register',identity[0].id,response)

@router.post('/account/passkeys')
def passkey_add(body:dict,request:Request,identity=Depends(current),db=Depends(get_db)):
    passkeys.complete_passkey_registration(db,identity[0],challenge=consume(db,request,body.get('challenge_id'),'register',identity[0].id),browser_credential=body.get('credential',{}),device_name=str(body.get('name','Passkey'))[:120]);return {'ok':True}

@router.delete('/account/passkeys/{key_id}')
def passkey_delete(key_id:int,identity=Depends(current),db=Depends(get_db)):
    passkeys.delete_passkey(db,user_id=identity[0].id,passkey_id=key_id);return {'ok':True}

@router.patch('/account')
def update_account(body:dict,identity=Depends(current),db=Depends(get_db)):
    u=identity[0]
    if 'name' in body:accounts.update_profile_name(db,u,str(body['name'])[:255])
    if 'username' in body:update_username(db,u,str(body['username'])[:80])
    if 'preferred_language' in body:
        accounts.update_preferences(db,u,preferred_language=body['preferred_language'],notifications_opt_in=body.get('notifications_opt_in') is True,marketing_opt_in=body.get('marketing_opt_in') is True)
    return profile(u)

@router.put('/account/payment')
def payment_details(body:dict,identity=Depends(current),db=Depends(get_db)):
    fields=['recipient_name','iban','bank_name','bic','revolut_link','payment_note']
    return profile(accounts.update_payment_details(db,identity[0],**{k:str(body.get(k) or '')[:500] for k in fields}))

def payment_profile_data(row):
    return {key:getattr(row,key) for key in ('id','label','recipient_name','iban','bank_name','bic','revolut_link','payment_note')}

@router.get('/account/payment-profiles')
def payment_profiles(identity=Depends(current),db=Depends(get_db)):
    from app.models.payment_profile import PaymentProfile
    return [payment_profile_data(row) for row in db.query(PaymentProfile).filter_by(user_id=identity[0].id).order_by(PaymentProfile.id).all()]

@router.post('/account/payment-profiles')
@router.put('/account/payment-profiles/{profile_id}')
def save_payment_profile(body:dict,profile_id:int|None=None,identity=Depends(current),db=Depends(get_db)):
    from app.models.payment_profile import PaymentProfile
    uid=identity[0].id
    row=db.query(PaymentProfile).filter_by(id=profile_id,user_id=uid).first() if profile_id else PaymentProfile(user_id=uid)
    if profile_id and not row:raise HTTPException(404,'Payment profile not found.')
    if not profile_id and db.query(PaymentProfile).filter_by(user_id=uid).count()>=20:raise ValueError('Maximum 20 payment profiles.')
    limits={'label':100,'recipient_name':255,'iban':64,'bank_name':255,'bic':32,'revolut_link':500,'payment_note':255}
    for key,limit in limits.items():
        value=body.get(key,'')
        if not isinstance(value,str) or len(value)>limit:raise ValueError('Invalid payment profile field: '+key)
        setattr(row,key,value.strip())
    if not row.label or not row.recipient_name or not (row.iban or row.revolut_link):
        raise ValueError('Enter a label, recipient and bank account or payment link.')
    if row.iban and (not row.bank_name or not __import__('re').fullmatch(r'[A-Za-z0-9 ]{15,64}',row.iban)):
        raise ValueError('Enter a bank name and valid IBAN characters.')
    if row.revolut_link and not row.revolut_link.startswith('https://'):
        raise ValueError('Payment links must use HTTPS.')
    db.add(row);db.commit();db.refresh(row)
    return payment_profile_data(row)

@router.delete('/account/payment-profiles/{profile_id}')
def delete_payment_profile(profile_id:int,identity=Depends(current),db=Depends(get_db)):
    from app.models.payment_profile import PaymentProfile
    row=db.query(PaymentProfile).filter_by(id=profile_id,user_id=identity[0].id).first()
    if not row:raise HTTPException(404,'Payment profile not found.')
    db.delete(row);db.commit();return {'deleted':True}

@router.post('/account/password')
def password(body:dict,request:Request,response:Response,identity=Depends(current),db=Depends(get_db)):
    u=accounts.set_password(db,identity[0],body.get('new_password',''),body.get('current_password',''))
    revoke_user(db,u.id);db.commit();return issue(db,u,request,response)

@router.post('/account/contact')
def contact(body:dict,identity=Depends(current),db=Depends(get_db)):
    r=accounts.request_contact_change(db,identity[0],body.get('channel'),body.get('value',''));return {k:v for k,v in r.items() if k!='debug_otp'}

@router.post('/account/contact/confirm')
def contact_confirm(body:dict,request:Request,response:Response,identity=Depends(current),db=Depends(get_db)):
    u=accounts.confirm_contact_change(db,identity[0],body.get('channel'),body.get('value',''),body.get('code',''),challenge_id=body.get('challenge_id',''))
    revoke_user(db,u.id);db.commit();return issue(db,u,request,response)

@router.post('/account/delete/request')
def delete_request(identity=Depends(current),db=Depends(get_db)):
    r=accounts.request_account_deletion_otp(db,identity[0]);return {k:v for k,v in r.items() if k!='debug_otp'}

@router.post('/account/delete/confirm')
def delete_confirm(body:dict,response:Response,identity=Depends(current),db=Depends(get_db)):
    u=identity[0]
    # Verify before deleting notification/session data.
    onboarding.verify_code(db,destination_type='email',destination=u.email,code=body.get('code',''),purpose='account_delete',challenge_id=body.get('challenge_id',''),user_id=u.id)
    revoke_user(db,u.id)
    from app.models.push_notification import PushDelivery,PushPreference,PushDevice,PushGrant
    ids=db.query(PushEvent.id).filter_by(user_id=u.id)
    db.query(PushDelivery).filter(PushDelivery.event_id.in_(ids)).delete(synchronize_session=False)
    db.query(PushEvent).filter_by(user_id=u.id).delete();db.query(PushPreference).filter_by(user_id=u.id).delete()
    db.query(PushDevice).filter_by(user_id=u.id).delete();db.query(PushGrant).filter_by(user_id=u.id).delete()
    from app.react_app.inbox import PruvsInboxRead
    db.query(PruvsInboxRead).filter_by(user_id=u.id).delete()
    from app.models.expense import ExpenseCompany,ExpenseReport,ExpenseTripProfile
    from app.models.history_visibility import HistoryVisibility
    db.query(ExpenseReport).filter_by(user_id=u.id).delete()
    db.query(ExpenseTripProfile).filter_by(user_id=u.id).delete()
    db.query(ExpenseCompany).filter_by(user_id=u.id).delete()
    db.query(HistoryVisibility).filter_by(user_id=u.id).delete()
    accounts.delete_user_completely(db,u)
    response.delete_cookie(COOKIE,path='/');response.delete_cookie(CSRF_COOKIE,path='/');return {'ok':True}

@router.get('/history')
def history(offset:int=Query(0,ge=0),view:str='active',identity=Depends(current),db=Depends(get_db)):
    from app.models.history_visibility import HistoryVisibility
    from app.react_app.receipt_labels import receipt_label
    if view not in ('active','archived','removed'):raise ValueError('Unknown history view.')
    uid=identity[0].id
    states={(r.kind,r.source_id):r for r in db.query(HistoryVisibility).filter_by(user_id=uid).all()}
    def include(kind,source_id):return (states.get((kind,source_id)).state if (kind,source_id) in states else 'active')==view
    case_query=db.query(Case).filter_by(user_id=uid).order_by(Case.created_at.desc())
    selected=[c for c in case_query.all() if include('receipt',c.id)]
    visible_bills=[b for b in bills.list_split_bill_sessions_for_user(db,uid,None) if include('bill',b['session_id'])]
    case_ids={c.id for c in selected}|{b['case_id'] for b in visible_bills}
    ordered=sorted(case_ids,key=lambda cid:(db.get(Case,cid).created_at,cid),reverse=True)
    page_ids=set(ordered[offset:offset+30])
    cases=[c for c in selected if c.id in page_ids]
    receipt_rows=[{**receipts.get_receipt_view(db,c.id,user_id=uid,ensure_translations=False),
                   'history_note':states.get(('receipt',c.id)).note if ('receipt',c.id) in states else ''} for c in cases]
    bill_rows=[{**b,'source_name':receipt_label(db,b['case_id']),
                'source_owned':db.get(Case,b['case_id']).user_id==uid,
                'history_note':states.get(('bill',b['session_id'])).note if ('bill',b['session_id']) in states else ''}
               for b in visible_bills if b['case_id'] in page_ids]
    return {'receipts':receipt_rows,'receipt_count':len(selected),'bills':bill_rows,
            'group_count':len(ordered),'group_order':ordered[offset:offset+30],
            'bill_counts':{'open':sum(b['status']=='open' for b in visible_bills),
                                               'settled':sum(b['status']=='settled' for b in visible_bills)}}

@router.post('/receipts/upload')
def upload(file:UploadFile=File(...),identity=Depends(current),db=Depends(get_db)):
    data=file.file.read(MAX_FILE_SIZE_BYTES+1)
    if len(data)>MAX_FILE_SIZE_BYTES:raise HTTPException(413,'Maximum upload size is 10 MB.')
    result=receipts.create_standalone_receipt_case(db,file_bytes=data,original_filename=file.filename or 'receipt.jpg',mime_type=file.content_type,user_id=identity[0].id,deduplicate=True)
    return {'case_id':result['case'].id,'duplicate':result.get('duplicate',False),'restored_original':result.get('restored_original',False)}

def owned_case(db,case_id,uid):
    c=db.get(Case,case_id)
    if not c or c.user_id!=uid:raise HTTPException(404,'Receipt not found.')
    return c

@router.get('/receipts/{case_id}')
def receipt(case_id:int,identity=Depends(current),db=Depends(get_db)):
    owned_case(db,case_id,identity[0].id)
    result=receipts.get_receipt_view(db,case_id,user_id=identity[0].id)
    result['has_split']=db.query(SplitBillSession).filter_by(case_id=case_id).first() is not None
    doc=db.query(Document).filter_by(case_id=case_id).order_by(Document.id.desc()).first()
    result['original_available']=resolve_document_path(doc) is not None
    return result

@router.get('/receipts/{case_id}/original')
def original(case_id:int,identity=Depends(current),db=Depends(get_db)):
    owned_case(db,case_id,identity[0].id)
    doc=db.query(Document).filter_by(case_id=case_id).order_by(Document.id.desc()).first()
    path=resolve_document_path(doc)
    if path is None:raise HTTPException(404,'Original file is unavailable. Upload your saved copy from this receipt page to restore it.')
    return FileResponse(path,filename=doc.original_filename or 'receipt',media_type=doc.mime_type or 'application/octet-stream',headers={'Cache-Control':'no-store'})

@router.post('/receipts/{case_id}/original/restore')
def restore_original(case_id:int,file:UploadFile=File(...),identity=Depends(current),db=Depends(get_db)):
    case=owned_case(db,case_id,identity[0].id)
    doc=db.query(Document).filter_by(case_id=case_id).order_by(Document.id.desc()).first()
    if resolve_document_path(doc):raise HTTPException(409,'This receipt already has a downloadable original.')
    data=file.file.read(MAX_FILE_SIZE_BYTES+1)
    if len(data)>MAX_FILE_SIZE_BYTES:raise HTTPException(413,'Maximum upload size is 10 MB.')
    saved=db.query(ReceiptFingerprint).filter_by(case_id=case_id,user_id=identity[0].id).first()
    if saved:
        sha,image_signature=fingerprint(data)
        if saved.sha256!=sha and not same_image(saved.image_signature,image_signature):
            raise HTTPException(422,'This file does not match the saved receipt. Choose the original receipt or a photo of it.')
    try:
        restore_missing_original(db,case,doc,data,file.filename or 'receipt.jpg',file.content_type)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    return {'case_id':case_id,'restored':True}

@router.put('/receipts/{case_id}/currency')
def currency(case_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    from app.services.receipt_currency_service import set_receipt_currency
    return {'currency':set_receipt_currency(db,case_id,identity[0].id,body.get('currency',''))}

@router.post('/receipts/{case_id}/split')
def create_split(case_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    owned_case(db,case_id,identity[0].id)
    session=bills.create_split_bill_session(db,case_id,identity[0].id,int(body.get('people',2)))
    return {'token':session.token}

def member(db,token,uid,owner=False,lock=False):
    query=db.query(SplitBillSession).filter_by(token=token)
    s=(query.with_for_update() if lock else query).first()
    if not s:raise HTTPException(404,'Bill not found.')
    p=db.query(SplitBillParticipant).filter_by(session_id=s.id,user_id=uid,status='joined').first()
    if not p or (owner and s.owner_user_id!=uid):raise HTTPException(403,'You do not have access to this bill action.')
    return s,p

def summary(db,s,uid):
    from app.react_app.receipt_labels import receipt_label
    result=bills.get_split_bill_session_summary(db,s,ensure_translations=False)
    result['source_name']=receipt_label(db,s.case_id)
    result['my_participant_id']=next(p['participant_id'] for p in result['participants'] if p['user_id']==uid)
    settings=json.loads(s.fx_settings_json) if s.fx_settings_json else None
    result['currency_reference']=settings
    if settings:
        from decimal import Decimal,ROUND_HALF_UP
        for participant in result['participants']:
            participant['reference_total']=str((Decimal(str(participant['total']))*Decimal(settings['rate'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
    if s.owner_user_id!=uid:
        for p in result['participants']:
            if p['user_id']!=uid:p.pop('phone_number',None)
    return result

@router.put('/bills/{token}/currency-reference')
def set_bill_currency_reference(token:str,body:dict,identity=Depends(current),db=Depends(get_db)):
    s,_=member(db,token,identity[0].id,owner=True,lock=True)
    from app.services.reference_fx import reference_quote
    target=str(body.get('target') or '').upper()
    from app.services.receipt_currency_service import CURRENCY_OPTIONS
    if target not in CURRENCY_OPTIONS:raise ValueError('Choose a currency from the list.')
    selected=reference_quote('1',s.currency,target,str(body.get('provider') or 'bnr'),body.get('manual_rate'))
    s.fx_settings_json=json.dumps({key:selected[key] for key in ('base','target','rate','date','provider','manual','source','source_url')})
    db.commit()
    return summary(db,s,identity[0].id)

@router.get('/bills/{token}/invite')
def invitation(token:str,identity=Depends(current),db=Depends(get_db)):
    from app.react_app.receipt_labels import receipt_label
    s=bills.get_split_bill_session_by_token(db,token)
    if not s:raise HTTPException(404,'Invitation not found.')
    mine=db.query(SplitBillParticipant).filter_by(session_id=s.id,user_id=identity[0].id,status='joined').first()
    owner=db.get(User,s.owner_user_id)
    return {'token':token,'owner':owner.name if owner else 'Pruvs user','source_name':receipt_label(db,s.case_id),
            'status':s.status,'joined':bool(mine),'is_owner':s.owner_user_id==identity[0].id}

@router.post('/bills/{token}/join')
def join(token:str,identity=Depends(current),db=Depends(get_db)):
    s=db.query(SplitBillSession).filter_by(token=token).with_for_update().first()
    if not s:raise HTTPException(404,'Invitation not found.')
    if s.owner_user_id==identity[0].id:raise ValueError('The owner is already part of this bill.')
    bills.join_split_bill_session_as_user(db,s,identity[0])
    from app.react_app.commerce import new_referral
    new_referral(db,s,identity[0])
    return summary(db,s,identity[0].id)

@router.get('/bills/{token}')
def bill(token:str,identity=Depends(current),db=Depends(get_db)):
    s,p=member(db,token,identity[0].id);return summary(db,s,identity[0].id)

@router.put('/bills/{token}/selection')
def selection(token:str,body:dict,identity=Depends(current),db=Depends(get_db)):
    s,p=member(db,token,identity[0].id,lock=True)
    quantities={int(k):float(v) for k,v in body.get('quantities',{}).items()}
    if len(quantities)>500 or any(not math.isfinite(v) or v<0 for v in quantities.values()):raise ValueError('Invalid item quantities.')
    bills.save_participant_selection(db,s,p.id,selected_quantities=quantities)
    from app.react_app.commerce import qualify_referral
    qualify_referral(db,s,identity[0],quantities)
    return summary(db,s,identity[0].id)

@router.post('/bills/{token}/action/{action}')
def bill_action(token:str,action:str,body:dict,identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id;s,p=member(db,token,uid,owner=action!='payment',lock=True)
    if action=='settle':
        from app.models.payment_profile import PaymentProfile
        selected=body.get('payment_profile_id')
        if selected is not None:
            if type(selected) is not int:raise ValueError('Choose a payment profile.')
            row=db.query(PaymentProfile).filter_by(id=selected,user_id=uid).first()
            if not row:raise ValueError('Choose one of your saved payment profiles.')
            details=payment_profile_data(row)
            details['payment_link']=details.pop('revolut_link')
        else:
            owner=identity[0]
            details={'recipient_name':owner.payment_recipient_name,'iban':owner.payment_iban,
                     'bank_name':owner.payment_bank_name,'bic':owner.payment_bic,
                     'revolut_payment_link':owner.revolut_payment_link,'payment_note':owner.payment_note}
        s.payment_details_json=json.dumps(details)
        bills.close_split_bill_session(db,s,uid)
    elif action=='reopen':bills.reopen_split_bill_session(db,s,uid)
    elif action=='tip':
        value=float(body.get('value',0))
        if not math.isfinite(value) or not 0<=value<=1000000:raise ValueError('Invalid tip amount.')
        bills.update_session_tip(db,s,uid,str(body.get('mode','none')),value)
    elif action=='people':bills.update_expected_participants_count(db,s,uid,int(body.get('people',2)))
    elif action=='remind':
        if int(body.get('participant_id',0))==p.id:raise ValueError('Reminders are for other participants.')
        bills.send_participant_reminder(db,s,uid,int(body.get('participant_id',0)),str(body.get('message','Please complete your Pruvs bill payment.'))[:500])
    elif action=='payment':bills.record_participant_payment_status(db,s,p.id,str(body.get('method','bank_transfer')),paid=body.get('paid') is True)
    else:raise HTTPException(404,'Unknown bill action.')
    return summary(db,s,uid)

@router.post('/device/subscribe')
def device_subscribe(body:dict,identity=Depends(current),db=Depends(get_db)):
    from app.services import push_service as push
    from app.models.push_notification import PushGrant
    if not push.enabled():raise HTTPException(503,'Device notifications are not configured yet.')
    grant=db.get(PushGrant,identity[1].token_hash)
    if not grant or not grant.active:raise HTTPException(401,'Sign in again to enable notifications.')
    subscription=push.validate_subscription(body.get('subscription'))
    identity[0].notifications_opt_in=True
    device=push.register_device(db,grant,subscription,str(body.get('label','Browser'))[:120])
    return {'device_id':device.id}

@router.get('/notifications/{event_id}/target')
def notification_target(event_id:str,identity=Depends(current),db=Depends(get_db)):
    from app.react_app.inbox import destination,mark,KINDS
    e=db.get(PushEvent,event_id);uid=identity[0].id
    if not e or e.user_id!=uid:raise HTTPException(404,'This notification is not available in your Inbox.')
    target='/inbox';message=None
    if e.kind in KINDS:
        target=destination(db,uid,e.url) or '/inbox'
        mark(db,uid,e)
        if target=='/inbox':message='Message marked read. This bill is no longer available to your account.'
    elif e.url.startswith('/receipt/'):
        try:
            cid=int(e.url.split('/')[2]);owned_case(db,cid,uid);target=f'/receipt/{cid}'
        except (ValueError,HTTPException):target='/history'
    e.read_at=datetime.utcnow();db.commit();return {'url':target,'message':message}

@router.get('/legal/{kind}')
def legal(kind:str,lang:str='en'):
    from app import legal_content as content
    if kind not in ('terms','privacy'):raise HTTPException(404,'Not found')
    prefix=kind.upper();suffix='_RO' if lang=='ro' else ''
    return {'title':getattr(content,prefix+'_TITLE'+suffix),'version':getattr(content,prefix+'_VERSION'),'sections':getattr(content,prefix+'_SECTIONS'+suffix)}
