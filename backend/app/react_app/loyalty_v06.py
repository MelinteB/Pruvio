"""Pruvs v0.6 customer-side, explicitly consented receipt-to-merchant submission.

The merchant gets one downscaled, metadata-stripped JPEG and a small allowlist
of receipt fields, never a Pruvs session, storage URL or original document.
"""
import base64
import binascii
import hashlib
import hmac
import io
import json
import os
import secrets
from datetime import datetime, timezone
import time
from decimal import Decimal, InvalidOperation
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from app.db.database import get_db
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_fingerprint import ReceiptFingerprint
from app.services.receipt_duplicates import fingerprint, same_image
from app.react_app.auth import current
from app.services import standalone_app_service as receipts
from app.services.document_service import resolve_document_path
from app.services.receipt_storage import is_cloud, read_paid
from app.react_app.loyalty_gateway import config,enabled,pseudonym,call_business,_base64url

router=APIRouter()
MAX_UPLOAD_B64=8_000_000
MAX_RECEIPT_IMAGE=180_000

class ClaimRequest(BaseModel):
    program_id:str=Field(min_length=36,max_length=36)
    code:str=Field(min_length=24,max_length=24,pattern=r'^[A-Fa-f0-9]{24}$')
    share_consent:bool
    photo_base64:str|None=Field(default=None,max_length=MAX_UPLOAD_B64)


def pilot_allowed(user_id):
    # Fail closed: v0.6 claims require an explicit customer allowlist.
    allowed={part.strip() for part in os.getenv('PRUVS_LOYALTY_RECEIPT_V06_PILOT_USER_IDS','').split(',') if part.strip()}
    return str(user_id) in allowed


def pilot_ready(user_id):
    if not pilot_allowed(user_id):
        raise HTTPException(403,'This receipt verification pilot is limited to invited accounts')
    if (not enabled() or os.getenv('PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED','false').lower()!='true'
            or os.getenv('PRUVS_LOYALTY_RECEIPT_V06_ENABLED','false').lower()!='true'):
        raise HTTPException(503,'Verified receipt submissions are not enabled in this environment')


def image_to_jpeg(raw):
    if not raw or len(raw)>6_000_000:raise HTTPException(413,'Receipt image exceeds 6 MB')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('JPEG','PNG','WEBP'):
                raise HTTPException(422,'Use a JPG, PNG or WebP receipt photo')
            if source.width*source.height>20_000_000:
                raise HTTPException(413,'Receipt photo resolution is too large')
            image=ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((850,1350),Image.Resampling.LANCZOS)
            # Re-encode pixels only: EXIF, GPS, ICC profiles and source metadata removed.
            for quality in (76,64,52,42):
                out=io.BytesIO()
                image.save(out,format='JPEG',quality=quality,optimize=True)
                if len(out.getvalue())<=MAX_RECEIPT_IMAGE:
                    return out.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError,Image.DecompressionBombError,OSError,ValueError):
        raise HTTPException(422,'Receipt photo could not be processed') from None
    raise HTTPException(413,'The receipt is too detailed for a secure preview. Upload a clear, cropped photo.')


def original_photo(db,case_id,uid):
    doc=db.query(Document).filter_by(case_id=case_id).order_by(Document.id.desc()).first()
    if not doc:raise HTTPException(422,'Receipt image unavailable. Upload a photo in the submission window.')
    if is_cloud(doc):return read_paid(doc,user_id=uid,case_id=case_id)
    path=resolve_document_path(doc)
    if path is not None and path.is_file():
        if path.stat().st_size>6_000_000:raise HTTPException(413,'Receipt image exceeds 6 MB')
        return path.read_bytes()
    raise HTTPException(422,'Original is stored on your device. Choose the receipt photo to share.')


def signed_proof(secret,uid,case_id,store_id,amount,currency,sha,merchant_label,receipt_date):
    now=int(time.time())
    body={'iss':'pruvs-core','aud':'pruvs-business','typ':'receipt_proof_v06',
          'sub':pseudonym(secret,'customer-v1',uid),
          'receipt_id':pseudonym(secret,'receipt-v1',f'{uid}:{case_id}'),
          'store_id':store_id,'amount_minor':amount,'currency':currency,
          'consent':True,'evidence_sha256':sha,'merchant_label':merchant_label,
          'receipt_date':receipt_date,
          'iat':now,'exp':now+300,'jti':secrets.token_hex(16)}
    a=_base64url(json.dumps({'alg':'HS256','typ':'JWT'},separators=(',',':')).encode())
    b=_base64url(json.dumps(body,separators=(',',':')).encode())
    sig=_base64url(hmac.new(secret.encode(),f'{a}.{b}'.encode(),hashlib.sha256).digest())
    return f'{a}.{b}.{sig}'

@router.post('/receipts/{case_id}/claim-v06',status_code=201)
def claim_v06(case_id:int,payload:ClaimRequest,identity=Depends(current),db=Depends(get_db)):
    pilot_ready(identity[0].id)
    if payload.share_consent is not True:
        raise HTTPException(422,'Consent is required to share this receipt with the merchant')
    try:program_id=str(UUID(payload.program_id))
    except (ValueError,AttributeError):raise HTTPException(422,'Invalid loyalty program') from None
    uid=identity[0].id
    case=db.get(Case,case_id)
    if not case or case.user_id!=uid:raise HTTPException(404,'Receipt not found')
    if case.status in ('failed','processing_failed','processing','pending'):
        raise HTTPException(422,'Receipt processing is not complete')
    detail=receipts.get_receipt_view(db,case_id,user_id=uid,ensure_translations=False)
    currency=str(detail.get('currency') or '').upper()
    if currency!='RON':raise HTTPException(422,'Only RON receipts are supported')
    try:
        value=Decimal(str(detail.get('receipt_total')))
        if not value.is_finite() or value<=0 or value*100!=(value*100).to_integral_value():raise ValueError()
        amount=int(value*100)
        if amount>10_000_000:raise ValueError()
    except (TypeError,ValueError,InvalidOperation):
        raise HTTPException(422,'Receipt amount is missing or invalid') from None
    preview=call_business('/v1/customer/pilot/purchases/preview',method='POST',user_id=uid,
                          body={'program_id':program_id,'code':payload.code.upper()})
    if preview.get('amount_minor')!=amount or preview.get('currency')!=currency:
        raise HTTPException(422,'Receipt total does not match the merchant purchase code')
    store_id=preview.get('store_id')
    if not isinstance(store_id,str) or not store_id:raise HTTPException(502,'Merchant verification unavailable')
    if payload.photo_base64:
        try:raw=base64.b64decode(payload.photo_base64,validate=True)
        except (binascii.Error,ValueError):raise HTTPException(422,'Invalid uploaded receipt photo') from None
        saved=db.query(ReceiptFingerprint).filter_by(case_id=case_id,user_id=uid).first()
        if not saved:
            raise HTTPException(422,'Cannot verify the uploaded photo against this receipt. Use the original stored receipt.')
        sha,sig=fingerprint(raw)
        if saved.sha256!=sha and not same_image(saved.image_signature,sig):
            raise HTTPException(422,'Uploaded photo does not match the scanned receipt. Use its original photo.')
    else:
        raw=original_photo(db,case_id,uid)
    image=image_to_jpeg(raw)
    merchant_label=str(detail.get('merchant_name') or 'Receipt')[:160].strip() or 'Receipt'
    receipt_date=str(detail.get('receipt_date') or detail.get('scan_date') or detail.get('date') or '')[:32]
    sha=hashlib.sha256(image).hexdigest()
    _,secret=config()
    proof=signed_proof(secret,uid,case_id,store_id,amount,currency,sha,merchant_label,receipt_date)
    return call_business('/v1/customer/pilot/claims/v06',method='POST',user_id=uid,
                body={'program_id':program_id,'code':payload.code.upper(),'receipt_proof':proof,
                      'evidence':{'consent':True,'merchant_label':merchant_label,
                       'receipt_date':receipt_date,'image_base64':base64.b64encode(image).decode('ascii')}})

@router.get('/claims')
def my_claims(identity=Depends(current)):
    pilot_ready(identity[0].id)
    return call_business('/v1/customer/pilot/claims',user_id=identity[0].id)


# Optional Core v7.1.49 customer-generated receipt code pilot.
# Runs exclusively server-side and uses the existing signed evidence transport.
class CustomerCodeRequest(BaseModel):
    program_id:str=Field(min_length=36,max_length=36)
    share_consent:bool
    photo_base64:str|None=Field(default=None,max_length=MAX_UPLOAD_B64)

@router.post('/receipts/{case_id}/customer-code-v12',status_code=201)
def customer_code_v12(case_id:int,payload:CustomerCodeRequest,identity=Depends(current),db=Depends(get_db)):
    pilot_ready(identity[0].id)
    if os.getenv('PRUVS_LOYALTY_CUSTOMER_CODES_V12_ENABLED','false').lower()!='true':
        raise HTTPException(503,'Customer receipt codes pilot is not enabled')
    if payload.share_consent is not True:
        raise HTTPException(422,'Consent is required to share this receipt with the merchant')
    try:program_id=str(UUID(payload.program_id))
    except (ValueError,AttributeError):raise HTTPException(422,'Invalid loyalty program') from None
    uid=identity[0].id
    case=db.get(Case,case_id)
    if not case or case.user_id!=uid:raise HTTPException(404,'Receipt not found')
    if case.status in ('failed','processing_failed','processing','pending'):
        raise HTTPException(422,'Receipt processing is not complete')
    detail=receipts.get_receipt_view(db,case_id,user_id=uid,ensure_translations=False)
    currency=str(detail.get('currency') or '').upper()
    if currency!='RON':raise HTTPException(422,'Only RON receipts are supported')
    try:
        value=Decimal(str(detail.get('receipt_total')))
        if not value.is_finite() or value<=0 or value*100!=(value*100).to_integral_value():raise ValueError()
        amount=int(value*100)
        if amount>10_000_000:raise ValueError()
    except (TypeError,ValueError,InvalidOperation):
        raise HTTPException(422,'Receipt amount is missing or invalid') from None
    eligible=call_business('/v1/customer/pilot/programs/'+program_id+'/receipt-eligibility-v12',
                           method='GET',user_id=uid)
    if eligible.get('currency')!=currency or amount<int(eligible.get('min_purchase_minor') or 0):
        raise HTTPException(422,'Receipt does not meet the program currency or minimum amount')
    store_id=eligible.get('store_id')
    if not isinstance(store_id,str) or not store_id:raise HTTPException(502,'Merchant program validation unavailable')
    if payload.photo_base64:
        try:raw=base64.b64decode(payload.photo_base64,validate=True)
        except (binascii.Error,ValueError):raise HTTPException(422,'Invalid uploaded receipt photo') from None
        saved=db.query(ReceiptFingerprint).filter_by(case_id=case_id,user_id=uid).first()
        if not saved:raise HTTPException(422,'Cannot verify this photo against your saved receipt')
        sha,sig=fingerprint(raw)
        if saved.sha256!=sha and not same_image(saved.image_signature,sig):
            raise HTTPException(422,'Uploaded photo does not match the saved receipt')
    else:raw=original_photo(db,case_id,uid)
    image=image_to_jpeg(raw)
    label=str(detail.get('merchant_name') or 'Receipt')[:160].strip() or 'Receipt'
    date=str(detail.get('receipt_date') or detail.get('scan_date') or detail.get('date') or '')[:32]
    digest=hashlib.sha256(image).hexdigest()
    _,secret=config()
    proof=signed_proof(secret,uid,case_id,store_id,amount,currency,digest,label,date)
    # The 96-bit random code is returned once to the authenticated customer.
    # Business sees only its digest, never the plaintext code via Core's bridge.
    code=secrets.token_hex(12).upper()
    result=call_business('/v1/customer/pilot/claims/v12/customer-code',method='POST',user_id=uid,
                body={'program_id':program_id,
                      'code_hash':hashlib.sha256(('v12:'+code).encode('ascii')).hexdigest(),
                      'receipt_proof':proof,
                      'evidence':{'consent':True,'merchant_label':label,'receipt_date':date,
                                  'image_base64':base64.b64encode(image).decode('ascii')}})
    return {'display_code':'PRV-'+'-'.join(code[i:i+4] for i in range(0,len(code),4)),
            'expires_at':result['expires_at'],'status':'pending',
            'claim_id':result['claim_id'],
            'message':'Show the code to the merchant for review. No reward until approved.'}
