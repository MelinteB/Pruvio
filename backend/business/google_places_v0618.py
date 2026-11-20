"""Google Places (New) merchant location discovery and opt-in place links.

- Google key stays server-side; routes are authenticated and input bounded.
- Only the Google Place ID is persisted. Ratings, reviews, names, photos and
  addresses from Google are requested live with attribution and no-store.
- Google Maps text search and details are chargeable; use explicit actions.
- No unreviewed auto-import into Pruvs merchant-owned business records.
"""
import logging, os
import re
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Staff, Store
from .models_v0618 import MerchantStorePlace
from .security import merchant_actor, customer_actor
from .pilot_v05 import can_manage

router=APIRouter(tags=['Google Maps location management'])
logger=logging.getLogger(__name__)
GOOGLE_ORIGIN='https://places.googleapis.com/v1'
PLACE_ID=re.compile(r'^[A-Za-z0-9_-]{8,255}$')
SEARCH_MASK='places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri'
DETAIL_MASK='id,displayName,formattedAddress,location,googleMapsUri,rating,userRatingCount,reviews.authorAttribution,reviews.rating,reviews.text,reviews.publishTime'

def configured_key():
    key=os.getenv('PRUVS_GOOGLE_PLACES_API_KEY','').strip()
    if not key:
        raise HTTPException(503,'Google Places is not configured for this environment.')
    return key

def allowed_place_id(place_id):
    if not PLACE_ID.fullmatch(place_id or ''):
        raise HTTPException(422,'Invalid Google Place ID.')
    return place_id

def _call(method,url,*,json_data=None,mask=DETAIL_MASK,language='en'):
    headers={'X-Goog-Api-Key':configured_key(),'X-Goog-FieldMask':mask,
             'Content-Type':'application/json'}
    try:
        with httpx.Client(timeout=8,follow_redirects=False) as client:
            result=client.request(method,url,headers=headers,
                                  params={'languageCode':language} if method=='GET' else None,
                                  json=json_data)
        if result.status_code==429:
            raise HTTPException(503,'Google Places quota reached. Retry later.')
        if result.status_code in (401,403):
            logger.warning('Google Places rejected the configured key (status=%s)',result.status_code)
            raise HTTPException(503,'Google Places rejected the configured key. Check Places API (New), billing and server-key restrictions.')
        if result.status_code==400:
            logger.warning('Google Places rejected the lookup request (status=400)')
            raise HTTPException(502,'Google Places rejected the lookup request. Check the Places API configuration.')
        if result.status_code!=200:
            logger.warning('Google Places lookup failed (status=%s)',result.status_code)
            raise HTTPException(502,'Google Places lookup is temporarily unavailable.')
        response=result.json()
        if not isinstance(response,dict):
            raise ValueError('Unexpected Places response')
        return response
    except HTTPException:
        raise
    except (httpx.HTTPError,ValueError):
        raise HTTPException(502,'Google Places could not be reached.') from None

def normalized(place,*,detail=False):
    place_id=place.get('id') or ''
    if not PLACE_ID.fullmatch(place_id):
        return None
    position=place.get('location') or {}
    url='https://www.google.com/maps/search/?'+urlencode({'api':'1','query':place_id,'query_place_id':place_id})
    display=(place.get('displayName') or {}).get('text','')
    out={'place_id':place_id,'name':display,'address':place.get('formattedAddress',''),
         'latitude':position.get('latitude'),'longitude':position.get('longitude'),
         'maps_url':url,'attribution':'Google Maps'}
    if detail:
        out['rating']=place.get('rating')
        out['user_rating_count']=place.get('userRatingCount')
        out['reviews']=[{
          'rating':r.get('rating'),
          'text':(r.get('text') or {}).get('text','')[:750],
          'author_name':(r.get('authorAttribution') or {}).get('displayName',''),
          'author_url':(r.get('authorAttribution') or {}).get('uri'),
          'published_at':r.get('publishTime')
        } for r in (place.get('reviews') or [])[:5]]
    return out

def lookup(place_id,language='en'):
    place_id=allowed_place_id(place_id)
    result=_call('GET',GOOGLE_ORIGIN+'/places/'+place_id,
                 language=language,mask=DETAIL_MASK)
    item=normalized(result,detail=True)
    if not item:
        raise HTTPException(404,'Place unavailable.')
    return item

def link_schema_ready(db):
    try:
        return inspect(db.get_bind()).has_table('merchant_store_google_place_v0618')
    except Exception:
        return False

def linked_place_id(db,store_id):
    if not link_schema_ready(db):
        return None
    return db.scalar(select(MerchantStorePlace.place_id).where(
        MerchantStorePlace.store_id==store_id))

def validate_store_place(db, place_id):
    if not link_schema_ready(db):
        raise HTTPException(503, 'Place-link database migration b12 is required.')
    return lookup(place_id)

@router.get('/v1/merchant/places/readiness')
def places_readiness(staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    return {'places_search_enabled':bool(os.getenv('PRUVS_GOOGLE_PLACES_API_KEY','').strip()),
            'place_links_migrated':link_schema_ready(db)}

@router.get('/v1/merchant/places/search')
def merchant_place_search(q:str=Query(min_length=3,max_length=120),
                          language:str=Query(default='en',pattern='^(en|ro)$'),
                          staff:Staff=Depends(merchant_actor)):
    can_manage(staff)
    query = q.strip()
    if len(query) < 3:
        raise HTTPException(422, 'Enter at least three characters to search Google Maps.')
    data=_call('POST',GOOGLE_ORIGIN+'/places:searchText',
       json_data={'textQuery':query,'languageCode':language,'pageSize':8},
       mask=SEARCH_MASK)
    return JSONResponse(
       {'places':[row for p in data.get('places',[]) if (row:=normalized(p))]},
       headers={'Cache-Control':'private, no-store'})

class PlaceLinkRequest(BaseModel):
    place_id:str=Field(min_length=8,max_length=255)

@router.post('/v1/merchant/stores/{store_id}/google-place')
def link_merchant_place(store_id:str,payload:PlaceLinkRequest,
                        staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    can_manage(staff)
    store=db.get(Store,store_id)
    if not store or store.merchant_id!=staff.merchant_id:
        raise HTTPException(404,'Location not found.')
    item=validate_store_place(db, payload.place_id)
    row=db.get(MerchantStorePlace,store.id)
    if row:
        row.place_id=item['place_id']
    else:
        db.add(MerchantStorePlace(store_id=store.id,merchant_id=staff.merchant_id,
                                  place_id=item['place_id']))
    db.commit()
    return {'store_id':store.id,'place_id':item['place_id'],'place':item,
            'notice':'Google-provided place details are not stored in Pruvs.'}

@router.delete('/v1/merchant/stores/{store_id}/google-place')
def unlink_merchant_place(store_id:str,staff:Staff=Depends(merchant_actor),
                          db:Session=Depends(get_db)):
    can_manage(staff)
    store=db.get(Store,store_id)
    if not store or store.merchant_id!=staff.merchant_id:
        raise HTTPException(404,'Location not found.')
    if not link_schema_ready(db):
        raise HTTPException(503,'Place links are not configured.')
    linked=db.get(MerchantStorePlace,store.id)
    if linked:db.delete(linked);db.commit()
    return {'unlinked':True,'store_id':store.id}

@router.get('/v1/merchant/places/{place_id}')
def merchant_place_details(place_id:str,language:str=Query(default='en',pattern='^(en|ro)$'),
                           staff:Staff=Depends(merchant_actor)):
    details=lookup(place_id,language)
    return JSONResponse(details,headers={'Cache-Control':'private, no-store'})

@router.get('/v1/customer/places/{place_id}')
def customer_place_details(place_id:str,language:str=Query(default='en',pattern='^(en|ro)$'),
                           consumer_id:str=Depends(customer_actor)):
    # Customer session required; avoid an unauthenticated public quota endpoint.
    details=lookup(place_id,language)
    return JSONResponse(details,headers={'Cache-Control':'private, no-store'})
