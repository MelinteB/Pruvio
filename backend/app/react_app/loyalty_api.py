"""Pruvs customer-facing Rewards API; authenticated and same-origin only."""
from fastapi import APIRouter, Depends, Query, HTTPException
from app.react_app.auth import current
from app.db.database import get_db
from app.models.case import Case
from app.services import standalone_app_service as receipts
from app.react_app.loyalty_gateway import call_business, config, enabled

router = APIRouter(prefix='/api/v1/loyalty', tags=['Rewards'])

@router.get('/status')
def status(identity=Depends(current)):
    # No Business secrets, tokens, or user IDs are exposed.
    return {'enabled':enabled(), 'receipt_claims_enabled':False,
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
    config()  # do not expose a pilot page accidentally when disabled
    uid = identity[0].id
    cases = db.query(Case).filter_by(user_id=uid).order_by(Case.created_at.desc()).limit(20).all()
    result = []
    for case in cases:
        data = receipts.get_receipt_view(db,case.id,user_id=uid,ensure_translations=False)
        result.append({'case_id':case.id,
                       'merchant_name':str(data.get('merchant_name') or 'Unknown merchant')[:160],
                       'receipt_total':data.get('receipt_total'),
                       'currency':data.get('currency'),
                       'matched_to_store':False})
    return {'receipts':result,'claiming_available':False,
            'message':'A merchant/POS receipt reference must be verified before earning loyalty rewards.'}
