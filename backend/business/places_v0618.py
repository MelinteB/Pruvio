"""Opt-in, merchant-scoped Google Places (New) integration.

Google place IDs may be stored; provider reviews, ratings, names and addresses
are fetched live and never copied into the merchant location-link table.
API keys remain server-side. Do not call this module from receipt/payment logic.
See Google Maps Platform EEA terms, data retention and attribution requirements.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, ForeignKey, DateTime, select, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session

from .db import Base, get_db
from .models import Merchant, Staff, Store, Program, Promotion
from .security import merchant_actor, customer_actor

router=APIRouter(tags=['Pruvs places v0.6.18'])
TABLE='merchant_store_places_v0618'
ID_PATTERN=re.compile(r'^[A-Za-z0-9_-]{8,260}$')
PLACES='https://places.googleapis.com/v1/'
SEARCH_FIELDS='places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri'
DETAIL_FIELDS=('id,displayName,formattedAddress,location,googleMapsUri,'
               'rating,userRatingCount,reviews,websiteUri,nationalPhoneNumber')

class StorePlaceLink(Base):
    __tablename__=TABLE
    store_id:Mapped[str]=mapped_column(String(36),ForeignKey('stores.id'),primary_key=True)
    merchant_id:Mapped[str]=mapped_column(String(36),ForeignKey('merchants.id'),nullable=False,index=True)
    place_id:Mapped[str]=mapped_column(String(260),nullable=False)
    linked_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,
                                             default=lambda:datetime.now(timezone.utc))

class LinkPlaceIn(BaseModel):
    place_id:str=Field(min_length=8,max_length=260)

def enabled():
    if os.getenv('PRUVS_BUSINESS_PLACES_ENABLED','false').lower()!='true':
        raise HTTPException(503,'Google Places integration is not enabled')

def credentials():
    enabled()
    key=os.getenv('GOOGLE_PLACES_SERVER_API_KEY','').strip()
    if len(key)<20:
        raise HTTPException(503,'Places server credentials are not configured')
    return key

def ready(db):
    if not inspect(db.get_bind()).has_table(TABLE):
        raise HTTPException(503,'Location linking migration b12a0618place is required')

def checked_id(place_id):
    if not isinstance(place_id,str) or not ID_PATTERN.fullmatch(place_id):
        raise HTTPException(422,'Invalid Google place ID')
    return place_id

def provider_json(path,mask,*,body=None):
    key=credentials()
    payload=json.dumps(body).encode('utf-8') if body is not None else None
    req=Request(PLACES+path,data=payload,method='POST' if body is not None else 'GET',
                headers={'X-Goog-Api-Key':key,'X-Goog-FieldMask':mask,
                         'Content-Type':'application/json','Accept':'application/json',
                         'User-Agent':'PruvsBusiness/0.6.18'})
    try:
        with urlopen(req,timeout=8) as response:
            raw=response.read(100001)
            if len(raw)>100000:raise HTTPException(502,'Places provider response too large')
            value=json.loads(raw)
            if not isinstance(value,dict):raise HTTPException(502,'Places provider returned invalid data')
            return value
    except HTTPError as e:
        if e.code in (403,429):
            raise HTTPException(503,'Places key, billing, quota or permissions need administrator review') from None
        raise HTTPException(502,'Places search is currently unavailable') from None
    except (URLError,TimeoutError,OSError,ValueError,UnicodeError):
        raise HTTPException(503,'Places search is temporarily unavailable') from None

def clean_place(p,with_reviews=False):
    name=p.get('displayName')
    coordinate=p.get('location') or {}
    value={'place_id':p.get('id'),'name':name.get('text','') if isinstance(name,dict) else '',
           'address':p.get('formattedAddress') or '',
           'latitude':coordinate.get('latitude'),'longitude':coordinate.get('longitude'),
           'google_maps_url':p.get('googleMapsUri') or ''}
    if with_reviews:
        value.update(rating=p.get('rating'),rating_count=p.get('userRatingCount'),
                     website=p.get('websiteUri') or '',phone=p.get('nationalPhoneNumber') or '')
        reviews=[]
        for rv in (p.get('reviews') or [])[:3]:
            author=rv.get('authorAttribution') or {}
            txt=rv.get('text') or {}
            reviews.append({'author':author.get('displayName') or '',
                            'author_url':author.get('uri') or '',
                            'rating':rv.get('rating'),'text':txt.get('text') or '',
                            'relative_time':rv.get('relativePublishTimeDescription') or ''})
        value['reviews']=reviews
    return value

@router.get('/v1/merchant/places/search')
def search_places(query:str=Query(min_length=3,max_length=110),
                  language:str=Query('en',pattern='^(en|ro)$'),
                  staff:Staff=Depends(merchant_actor)):
    if staff.role not in ('owner','manager'):
        raise HTTPException(403,'Merchant manager required')
    response=provider_json('places:searchText',SEARCH_FIELDS,body={
        'textQuery':query.strip(),'languageCode':language,'regionCode':'RO',
        'pageSize':6})
    return {'places':[clean_place(p) for p in response.get('places',[]) if p.get('id')],
            'source':'Google Maps','cache':'no-store'}

@router.get('/v1/merchant/places/{place_id}')
def get_place_details(place_id:str,staff:Staff=Depends(merchant_actor)):
    if staff.role not in ('owner','manager'):
        raise HTTPException(403,'Merchant manager required')
    return {**clean_place(provider_json('places/'+checked_id(place_id),DETAIL_FIELDS),True),
            'source':'Google Maps','cache':'no-store'}

@router.post('/v1/merchant/stores/{store_id}/place')
def link_store_place(store_id:str,body:LinkPlaceIn,staff:Staff=Depends(merchant_actor),
                     db:Session=Depends(get_db)):
    if staff.role not in ('owner','manager'):
        raise HTTPException(403,'Merchant manager required')
    ready(db)
    store=db.get(Store,store_id)
    if not store or store.merchant_id!=staff.merchant_id:
        raise HTTPException(404,'Location not found')
    checked_id(body.place_id)
    # Validate against Google instead of trusting the browser or allowing arbitrary IDs.
    place=clean_place(provider_json('places/'+body.place_id,
                                    'id,displayName,formattedAddress,location'))
    if place.get('place_id')!=body.place_id or place.get('latitude') is None:
        raise HTTPException(422,'Place is no longer available')
    link=db.get(StorePlaceLink,store.id)
    if not link:
        link=StorePlaceLink(store_id=store.id,merchant_id=staff.merchant_id,
                            place_id=body.place_id)
        db.add(link)
    else:
        link.place_id=body.place_id
    db.commit()
    return {'store_id':store.id,'place_id':body.place_id,'source':'Google Maps'}

@router.get('/v1/merchant/stores/{store_id}/place')
def get_store_place(store_id:str,staff:Staff=Depends(merchant_actor),
                    db:Session=Depends(get_db)):
    ready(db)
    store=db.get(Store,store_id)
    if not store or store.merchant_id!=staff.merchant_id:
        raise HTTPException(404,'Location not found')
    link=db.get(StorePlaceLink,store.id)
    if not link:return {'place_id':None}
    return get_place_details(link.place_id,staff)

def public_linked_place(db,place_id):
    """Paid public place lookups are limited to a linked location with a live offer."""
    ready(db)
    now=datetime.now(timezone.utc)
    row=db.scalar(
        select(StorePlaceLink)
        .join(Store,StorePlaceLink.store_id==Store.id)
        .join(Merchant,Store.merchant_id==Merchant.id)
        .join(Program,Program.store_id==Store.id)
        .join(Promotion,Promotion.program_id==Program.id)
        .where(StorePlaceLink.place_id==place_id,Store.active.is_(True),
               Merchant.status=='active',Program.status=='published',
               Promotion.status=='published',Promotion.expires_at>now)
        .limit(1))
    if not row:raise HTTPException(404,'Place is not associated with a live campaign')

@router.get('/v1/places/{place_id}')
def public_place_summary(place_id:str,db:Session=Depends(get_db)):
    checked_id(place_id)
    enabled()
    public_linked_place(db,place_id)
    return {**clean_place(provider_json('places/'+place_id,DETAIL_FIELDS),True),
            'source':'Google Maps','cache':'no-store'}
