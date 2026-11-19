"""No-network Google Places tests: tenant isolation, safe URLs, API readiness."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from business.db import Base
from business.main import add_store
from business.models import Merchant,Store
from business.models_v0618 import MerchantStorePlace
from business.schemas import StoreIn
from business import google_places_v0618 as places

EXAMPLE_ID='ChIJxxxxxxxxxxxxxxx'

def test_place_ids_and_transient_reviews_are_usable_without_storage():
    place=places.normalized({
      'id':EXAMPLE_ID,
      'displayName':{'text':'Test Cafe'},
      'formattedAddress':'Example Street 1',
      'location':{'latitude':44.44,'longitude':26.11},
      'rating':4.6,'userRatingCount':123,
      'reviews':[{'rating':5,'text':{'text':'Good coffee'},
                  'authorAttribution':{'displayName':'Reviewer',
                                       'uri':'https://maps.google.com/example'}}]
    },detail=True)
    assert place['place_id']==EXAMPLE_ID
    assert place['rating']==4.6
    assert place['reviews'][0]['author_name']=='Reviewer'
    assert 'google.com/maps/search' in place['maps_url']
    assert 'query_place_id=' in place['maps_url']

def test_invalid_ids_fail_closed():
    for invalid in ('../etc','https://example.com','a','abc/def','" OR 1=1'):
        with pytest.raises(HTTPException):
            places.allowed_place_id(invalid)

def test_places_not_enabled_without_server_key(monkeypatch):
    monkeypatch.delenv('PRUVS_GOOGLE_PLACES_API_KEY',raising=False)
    with pytest.raises(HTTPException) as exc:
        places.configured_key()
    assert exc.value.status_code==503

@pytest.fixture
def tenant_db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine,autoflush=False) as db:
        a=Merchant(name='Owner');b=Merchant(name='Other')
        db.add_all([a,b]);db.flush()
        store=Store(merchant_id=a.id,name='Pruvs store',address='Manual Address',
                    latitude=44.5,longitude=26.2)
        db.add(store);db.commit()
        yield db,a,b,store
    engine.dispose()

def test_owner_can_link_place_id_only_without_google_content(monkeypatch,tenant_db):
    db,a,b,store=tenant_db
    monkeypatch.setattr(places,'lookup',lambda place_id: {
        'place_id':place_id,'name':'LIVE Provider Name',
        'address':'Never persist me','reviews':[{'text':'Never store me'}]})
    row=places.link_merchant_place(store.id,places.PlaceLinkRequest(place_id=EXAMPLE_ID),
             staff=SimpleNamespace(merchant_id=a.id,role='owner'),db=db)
    assert row['place_id']==EXAMPLE_ID
    link=db.scalar(select(MerchantStorePlace).where(MerchantStorePlace.store_id==store.id))
    assert link.place_id==EXAMPLE_ID
    assert db.get(Store,store.id).name=='Pruvs store'
    assert db.get(Store,store.id).address=='Manual Address'
    assert not hasattr(link,'reviews')
    assert places.linked_place_id(db,store.id)==EXAMPLE_ID
    result=places.unlink_merchant_place(store.id,
      staff=SimpleNamespace(merchant_id=a.id,role='owner'),db=db)
    assert result['unlinked']
    assert places.linked_place_id(db,store.id) is None

def test_cross_tenant_and_analyst_cannot_link(monkeypatch,tenant_db):
    db,a,b,store=tenant_db
    monkeypatch.setattr(places,'lookup',lambda place_id: {'place_id':place_id})
    for staff,expected in ((SimpleNamespace(merchant_id=b.id,role='owner'),404),
                           (SimpleNamespace(merchant_id=a.id,role='analyst'),403)):
        with pytest.raises(HTTPException) as exc:
            places.link_merchant_place(store.id,places.PlaceLinkRequest(place_id=EXAMPLE_ID),
               staff=staff,db=db)
        assert exc.value.status_code==expected

def test_pre_migration_link_is_controlled_503(monkeypatch,tenant_db):
    db,a,b,store=tenant_db
    monkeypatch.setattr(places,'link_schema_ready',lambda _db:False)
    with pytest.raises(HTTPException) as exc:
        places.link_merchant_place(store.id,places.PlaceLinkRequest(place_id=EXAMPLE_ID),
          staff=SimpleNamespace(merchant_id=a.id,role='owner'),db=db)
    assert exc.value.status_code==503


def test_new_location_and_google_link_save_together(monkeypatch, tenant_db):
    db, merchant, _, _ = tenant_db
    staff = SimpleNamespace(merchant_id=merchant.id, role='owner')

    def unavailable(_place_id):
        raise HTTPException(503, 'Google Places is not configured for this environment.')

    payload = StoreIn(name=' New Cafe ', address=' Manual Address ', latitude=44.5,
                      longitude=26.2, google_place_id=EXAMPLE_ID)
    monkeypatch.setattr(places, 'lookup', unavailable)
    with pytest.raises(HTTPException) as exc:
        add_store(payload, staff, db)
    assert exc.value.status_code == 503
    assert db.scalar(select(Store).where(Store.name == 'New Cafe')) is None
    assert db.scalar(select(MerchantStorePlace)) is None

    monkeypatch.setattr(places, 'lookup', lambda place_id: {'place_id': place_id, 'address': 'Google Address'})
    saved = add_store(payload, staff, db)
    assert saved['address'] == 'Manual Address'
    assert saved['google_place_id'] == EXAMPLE_ID
    assert db.get(MerchantStorePlace, saved['id']).merchant_id == merchant.id


def test_manual_location_can_save_without_google(monkeypatch, tenant_db):
    db, merchant, _, _ = tenant_db
    monkeypatch.delenv('PRUVS_GOOGLE_PLACES_API_KEY', raising=False)
    monkeypatch.setattr(places, 'link_schema_ready', lambda _db: False)
    saved = add_store(StoreIn(name='Manual Cafe', latitude=0, longitude=0),
                      SimpleNamespace(merchant_id=merchant.id, role='owner'), db)
    assert saved['google_place_id'] is None
    assert db.get(Store, saved['id']).name == 'Manual Cafe'
