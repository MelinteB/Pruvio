from datetime import datetime, timezone, timedelta
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from argon2 import PasswordHasher, exceptions
import jwt
from sqlalchemy.orm import Session
from .db import get_db
from .models import Staff, uid
from .config import get_settings

hasher = PasswordHasher()
optional_bearer = HTTPBearer(auto_error=False)

def encode_merchant_token(staff: Staff):
    cfg=get_settings()
    now=datetime.now(timezone.utc)
    return jwt.encode({'sub':staff.id,'iss':'pruvs-business','aud':'pruvs-business-merchant',
        'iat':now,'exp':now+timedelta(hours=2),'jti':uid()},cfg.business_jwt_secret,algorithm='HS256')

def decode(raw, key, issuer, audience, typ=None):
    try:
        payload=jwt.decode(raw,key,algorithms=['HS256'],issuer=issuer,audience=audience,
            options={'require':['exp','iat','sub','iss','aud','jti']},leeway=10)
        if typ and payload.get('typ')!=typ:
            raise ValueError('Wrong token purpose')
        return payload
    except (jwt.PyJWTError,ValueError) as ex:
        raise HTTPException(status_code=401,detail='Invalid or expired authentication') from ex

def require_token(creds: HTTPAuthorizationCredentials | None):
    if creds is None or creds.scheme.lower()!='bearer':
        raise HTTPException(401,'Authentication required')
    return creds.credentials

def merchant_actor(credentials: Annotated[HTTPAuthorizationCredentials | None,Depends(optional_bearer)],db:Session=Depends(get_db)) -> Staff:
    cfg=get_settings()
    payload=decode(require_token(credentials),cfg.business_jwt_secret,'pruvs-business','pruvs-business-merchant')
    staff=db.get(Staff,payload['sub'])
    if not staff or not staff.active:
        raise HTTPException(401,'Inactive merchant account')
    return staff

def customer_actor(credentials: Annotated[HTTPAuthorizationCredentials | None,Depends(optional_bearer)]) -> str:
    cfg=get_settings()
    payload=decode(require_token(credentials),cfg.pruvs_bridge_secret,'pruvs-core','pruvs-business','customer_session')
    return payload['sub']

def verify_password(password, password_hash):
    try:
        return hasher.verify(password_hash,password)
    except (exceptions.VerifyMismatchError,exceptions.VerificationError,exceptions.InvalidHashError):
        return False
