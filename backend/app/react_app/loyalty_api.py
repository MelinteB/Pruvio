"""Pruvs customer-facing Rewards API; authenticated and same-origin only."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from decimal import Decimal, InvalidOperation
import os
from app.react_app.auth import current
from app.db.database import get_db
from app.models.case import Case
from app.services import standalone_app_service as receipts
from app.react_app.loyalty_gateway import call_business, config, enabled, receipt_proof, pseudonym

router = APIRouter(prefix='/api/v1/loyalty', tags=['Rewards'])

@router.get('/status')
def status(identity=Depends(current)):
    # No Business secrets, tokens, or user IDs are exposed.
    return {'enabled':enabled(), 'receipt_claims_enabled':enabled() and os.getenv('PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED','false').lower()=='true',
            'receipt_v06_enabled':enabled() and os.getenv('PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED','false').lower()=='true' and os.getenv('PRUVS_LOYALTY_RECEIPT_V06_ENABLED','false').lower()=='true' and __import__('app.react_app.loyalty_v06',fromlist=['pilot_allowed']).pilot_allowed(identity[0].id),
            'message':'Receipt earning requires verified merchant integration and merchant approval.'}

@router.get('/offers')
def offers(latitude:float|None=Query(None,ge=-90,le=90),
           longitude:float|None=Query(None,ge=-180,le=180),
           radius_km:float=Query(10,gt=0,le=50),identity=Depends(current)):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422,'Both latitude and longitude are required.')
    params = {'radius_km': radius_km}
    if latitude is not None:
        params.update(latitude=latitude,longitude=longitude)
    return call_business('/v1/discover', params=params)

@router.post('/programs/{program_id}/join')
def join(program_id:str,identity=Depends(current)):
    from uuid import UUID
    try: program_id=str(UUID(program_id))
    except (ValueError,AttributeError): raise HTTPException(422, 'Invalid program ID.') from None
    return call_business('/v1/customer/programs/'+program_id+'/join', method='POST', user_id=identity[0].id)

@router.get('/wallet')
def wallet(identity=Depends(current)):
    return call_business('/v1/customer/wallet', user_id=identity[0].id)

@router.post('/rewards/{reward_id}/reserve')
def reserve(reward_id:str,identity=Depends(current)):
    from uuid import UUID
    try: reward_id=str(UUID(reward_id))
    except (ValueError,AttributeError): raise HTTPException(422, 'Invalid reward ID.') from None
    return call_business('/v1/customer/rewards/'+reward_id+'/reserve',method='POST',user_id=identity[0].id)

@router.get('/receipts')
def receipt_candidates(identity=Depends(current),db=Depends(get_db)):
    # View-only listing: no proof issuance from OCR merchant names.
    _url,bridge_secret=config()  # fail closed when Rewards are unavailable
    uid = identity[0].id
    cases = db.query(Case).filter_by(user_id=uid).order_by(Case.created_at.desc()).limit(20).all()
    result = []
    for case in cases:
        data = receipts.get_receipt_view(db,case.id,user_id=uid,ensure_translations=False)
        result.append({'case_id':case.id,
                       'merchant_name':str(data.get('merchant_name') or 'Unknown merchant')[:160],
                       'receipt_total':data.get('receipt_total'),
                       'currency':data.get('currency'),
                       'matched_to_store':False,
                       'receipt_ref':pseudonym(bridge_secret,'receipt-v1',f'{uid}:{case.id}')})
    return {'receipts':result,'claiming_available':False,
            'message':'A merchant/POS receipt reference must be verified before earning loyalty rewards.'}


@router.get('/promotions')
def promotions(limit:int=Query(12,ge=1,le=30), identity=Depends(current)):
    return call_business('/v1/promotions',params={'limit':limit})

class ReceiptClaimIn(BaseModel):
    program_id: str=Field(min_length=36,max_length=36)
    code: str=Field(min_length=24,max_length=24,pattern=r'^[A-Fa-f0-9]{24}$')

@router.post('/receipts/{case_id}/claim',status_code=201)
def claim_receipt(case_id:int, payload:ReceiptClaimIn, identity=Depends(current), db=Depends(get_db)):
    if not enabled() or os.getenv('PRUVS_LOYALTY_RECEIPT_CLAIMS_ENABLED','false').lower()!='true':
        raise HTTPException(503,'Receipt pilot is not enabled.')
    if os.getenv('PRUVS_LOYALTY_RECEIPT_V06_ENABLED','false').lower()=='true':
        raise HTTPException(409,'Use the updated secure receipt submission flow')
    from uuid import UUID
    try: program_id=str(UUID(payload.program_id))
    except (ValueError,AttributeError):raise HTTPException(422,'Invalid program') from None
    uid=identity[0].id
    case=db.get(Case,case_id)
    if not case or case.user_id!=uid:raise HTTPException(404,'Receipt not found')
    if case.status in ('failed','processing_failed','processing','pending'):
        raise HTTPException(422,'Receipt processing is not complete')
    detail=receipts.get_receipt_view(db,case.id,user_id=uid,ensure_translations=False)
    currency=str(detail.get('currency') or '').upper()
    if currency!='RON':raise HTTPException(422,'Only RON receipts supported for this pilot')
    try:
        amount=Decimal(str(detail.get('receipt_total')))
        if not amount.is_finite() or amount<=0 or amount*100!=(amount*100).to_integral_value():
            raise ValueError()
        minor=int(amount*100)
        if minor>10000000:raise ValueError()
    except (TypeError,ValueError,InvalidOperation):
        raise HTTPException(422,'Receipt total is missing or invalid') from None
    preview=call_business('/v1/customer/pilot/purchases/preview',user_id=uid,method='POST',
                          body={'program_id':program_id,'code':payload.code.upper()})
    if preview.get('amount_minor')!=minor or preview.get('currency')!=currency:
        raise HTTPException(422,'Receipt total does not match the merchant purchase code')
    store_id=preview.get('store_id')
    if not isinstance(store_id,str) or not store_id:raise HTTPException(502,'Merchant verification unavailable')
    _url,secret=config()
    proof=receipt_proof(secret,uid,case_id,store_id,minor,currency)
    return call_business('/v1/customer/pilot/claims',user_id=uid,method='POST',
                         body={'program_id':program_id,'code':payload.code.upper(),'receipt_proof':proof})

from app.react_app.loyalty_v06 import router as v06_router
router.include_router(v06_router)
