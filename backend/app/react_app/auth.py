import hashlib
import os
import secrets
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Request, Response
from app.db.database import get_db
from app.models.user import User
from app.models.react_session import ReactSession, ReactRateLimit
from app.models.push_notification import PushGrant, PushDevice

COOKIE='pruvs_session'
CSRF_COOKIE='pruvs_csrf'

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def secure(): return os.getenv('PUBLIC_BASE_URL','https://pruvs.io').startswith('https://')

def origin_allowed(origin):
    return origin == os.getenv('PUBLIC_BASE_URL','https://pruvs.io').rstrip('/')

def current(request:Request,db=Depends(get_db)):
    token=request.cookies.get(COOKIE,'')
    session=db.get(ReactSession,digest(token)) if token else None
    user=db.get(User,session.user_id,populate_existing=True) if session and session.expires_at>datetime.utcnow() else None
    if not user or user.status!='active':raise HTTPException(401,'Sign in to continue.')
    if request.method not in ('GET','HEAD','OPTIONS'):
        csrf=request.headers.get('X-CSRF-Token','')
        if not csrf or not secrets.compare_digest(digest(csrf),session.csrf_hash):raise HTTPException(403,'Session changed. Reload this page.')
        if request.headers.get('X-Pruvs-User') != str(user.id):raise HTTPException(409,'Account changed in another tab. Reload this page.')
    return user,session

def admin(identity=Depends(current)):
    if not identity[0].is_admin:raise HTTPException(403,'Administrator access is required.')
    return identity

def revoke(db,key):
    db.query(PushDevice).filter_by(grant_hash=key).update({'active':False,'test_hash':None})
    db.query(PushGrant).filter_by(token_hash=key).update({'active':False})
    db.query(ReactSession).filter_by(token_hash=key).delete()

def revoke_user(db,uid):
    db.query(PushDevice).filter_by(user_id=uid).update({'active':False,'test_hash':None})
    db.query(PushGrant).filter_by(user_id=uid).update({'active':False})
    db.query(ReactSession).filter_by(user_id=uid).delete()

def issue(db,user,request,response):
    if user.status!='active':raise HTTPException(401,'Account unavailable.')
    old=request.cookies.get(COOKIE)
    if old:revoke(db,digest(old))
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);expiry=datetime.utcnow()+timedelta(days=30)
    key=digest(token)
    db.add(ReactSession(token_hash=key,user_id=user.id,csrf_hash=digest(csrf),expires_at=expiry))
    db.add(PushGrant(token_hash=key,user_id=user.id,expires_at=expiry,active=True))
    db.commit()
    response.set_cookie(COOKIE,token,httponly=True,secure=secure(),samesite='lax',max_age=2592000,path='/')
    response.set_cookie(CSRF_COOKIE,csrf,httponly=False,secure=secure(),samesite='lax',max_age=2592000,path='/')
    return {'user':profile(user),'csrf':csrf}

def profile(u):
    fields=['id','name','username','email','phone_number','is_admin','status','is_email_verified',
            'preferred_language','notifications_opt_in','marketing_opt_in','payment_recipient_name',
            'payment_iban','payment_bank_name','payment_bic','revolut_payment_link','payment_note']
    return {k:getattr(u,k,None) for k in fields}

def limit(db,request,bucket,maximum=15):
    # The client connection address is used, not a caller-controlled forwarded header.
    key=digest(bucket+':'+(request.client.host if request.client else 'unknown'))
    now=datetime.utcnow()
    row=db.query(ReactRateLimit).filter_by(id=key).with_for_update().first()
    if not row:
        row=ReactRateLimit(id=key,count=0,reset_at=now+timedelta(minutes=10));db.add(row)
    if row.reset_at<=now:row.count=0;row.reset_at=now+timedelta(minutes=10)
    if row.count>=maximum:raise HTTPException(429,'Too many attempts. Try again in 10 minutes.')
    row.count+=1;db.commit()

def push_identity(identity=Depends(current),db=Depends(get_db)):
    user,session=identity
    grant=db.get(PushGrant,session.token_hash)
    if not grant or not grant.active:raise HTTPException(401,'Sign in again to set up notifications.')
    return grant
