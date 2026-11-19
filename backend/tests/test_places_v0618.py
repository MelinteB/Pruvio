"""Google Places integration tests use no real Google credentials or network."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session

from business.db import Base
from business.models import Merchant,Store,Program,Promotion
from business import places_v0618 as places

ROOT=Path(__file__).resolve().parents[1]
ID='ChIJabc123456789ABCDEFG'

@pytest.fixture
def db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        merchant=Merchant(name='Bistro',status='active')
        other=Merchant(name='Different owner',status='active')
        session.add_all((merchant,other));session.flush()
        store=Store(merchant_id=merchant.id,name='City Square',address='Bucharest',
                    latitude=44.42,longitude=26.10,active=True)
        session.add(store);session.flush()
        program=Program(merchant_id=merchant.id,store_id=store.id,
                        title='Three lunches',description='',stamps_required=3,
                        min_purchase_minor=1000,reward_minor=1000,currency='RON',status='published')
        session.add(program);session.commit()
        yield session,merchant,other,store,program
    engine.dispose()

def fake_provider(path,mask,*,body=None):
    response={
        'id':ID,
        'displayName':{'text':'Bistro Central'},
        'formattedAddress':'Bulevardul Unirii, București, România',
        'location':{'latitude':44.42,'longitude':26.10},
        'googleMapsUri':'https://maps.google.com/?cid=123',
        'rating':4.6,'userRatingCount':128,
        'reviews':[{'rating':5,'text':{'text':'Nice coffee'},
                    'authorAttribution':{'displayName':'Visitor','uri':'https://www.google.com/maps/'}}]}
    if path=='places:searchText':
        assert mask==places.SEARCH_FIELDS
        assert body['pageSize']<=6
        return {'places':[response]}
    assert path=='places/'+ID
    return response

def test_search_returns_provider_results_with_attribution(monkeypatch,db):
    session,merchant,*_=db
    monkeypatch.setattr(places,'provider_json',fake_provider)
    staff=SimpleNamespace(merchant_id=merchant.id,role='owner')
    data=places.search_places('Bistro Central','ro',staff=staff)
    assert len(data['places'])==1
    assert data['places'][0]['place_id']==ID
    assert data['source']=='Google Maps'
    assert 'reviews' not in data['places'][0]
    data=places.get_place_details(ID,staff=staff)
    assert data['rating']==4.6
    assert data['reviews'][0]['author']=='Visitor'
    assert data['reviews'][0]['text']=='Nice coffee'

def test_search_requires_owner_or_manager(monkeypatch,db):
    session,merchant,*_=db
    with pytest.raises(HTTPException) as e:
        places.search_places('Bistro Central',staff=SimpleNamespace(merchant_id=merchant.id,role='analyst'))
    assert e.value.status_code==403

def test_google_keys_are_server_only_and_integration_fails_closed(monkeypatch):
    monkeypatch.delenv('PRUVS_BUSINESS_PLACES_ENABLED',raising=False)
    with pytest.raises(HTTPException) as e:
        places.credentials()
    assert e.value.status_code==503
    monkeypatch.setenv('PRUVS_BUSINESS_PLACES_ENABLED','true')
    monkeypatch.delenv('GOOGLE_PLACES_SERVER_API_KEY',raising=False)
    with pytest.raises(HTTPException) as e:
        places.credentials()
    assert e.value.status_code==503

def test_place_association_is_tenant_scoped_and_no_reviews_are_stored(monkeypatch,db):
    session,merchant,other,store,program=db
    monkeypatch.setattr(places,'provider_json',fake_provider)
    staff=SimpleNamespace(merchant_id=merchant.id,role='owner')
    result=places.link_store_place(store.id,places.LinkPlaceIn(place_id=ID),staff=staff,db=session)
    assert result['place_id']==ID
    stored=session.get(places.StorePlaceLink,store.id)
    assert stored.place_id==ID
    assert not hasattr(stored,'rating')
    assert not hasattr(stored,'reviews')
    foreign=SimpleNamespace(merchant_id=other.id,role='owner')
    with pytest.raises(HTTPException) as e:
        places.link_store_place(store.id,places.LinkPlaceIn(place_id=ID),staff=foreign,db=session)
    assert e.value.status_code==404

def test_public_review_lookup_requires_active_published_campaign(monkeypatch,db):
    session,merchant,other,store,program=db
    monkeypatch.setenv('PRUVS_BUSINESS_PLACES_ENABLED','true')
    monkeypatch.setattr(places,'provider_json',fake_provider)
    staff=SimpleNamespace(merchant_id=merchant.id,role='owner')
    places.link_store_place(store.id,places.LinkPlaceIn(place_id=ID),staff=staff,db=session)
    with pytest.raises(HTTPException) as e:
        places.public_place_summary(ID,consumer_id='signed-customer',db=session)
    assert e.value.status_code==404
    now=datetime.now(timezone.utc)
    session.add(Promotion(merchant_id=merchant.id,program_id=program.id,
            headline='Visit the bistro',message='Three qualifying visits.',status='published',
            duration_days=14,published_at=now,expires_at=now+timedelta(days=3)))
    session.commit()
    public=places.public_place_summary(ID,consumer_id='signed-customer',db=session)
    assert public['rating']==4.6 and public['reviews'][0]['author']=='Visitor'
    store.active=False;session.commit()
    with pytest.raises(HTTPException) as e:
        places.public_place_summary(ID,consumer_id='signed-customer',db=session)
    assert e.value.status_code==404

def test_locations_have_real_management_and_no_fake_coordinates():
    src=(ROOT/'business_frontend/src/LocationManager.jsx').read_text()
    entry=(ROOT/'business_frontend/src/main.jsx').read_text()
    assert 'window.localStorage' in src
    assert 'Google Maps' in src
    assert 'Google rating & reviews' in src
    assert '44.4268' not in src
    assert "setLatitude(useState('44.4268'))" not in entry
    assert 'LocationManager' in entry
    assert "method:'PATCH'" not in entry or '/v1/merchant/stores/' in entry
    assert (ROOT/'business_migrations/versions/b12a0618_google_places_link.py').is_file()
