"""Business v0.6.11 campaign lifecycle and AI generation tests.

No customer DB, network request or real AI billable operation is used.
"""
import base64
import io
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business.db import Base
from business.models import Merchant, Program, Promotion, Staff, Store
from business import pilot_v05
from business import ai_campaign_artwork_v0611 as artwork
from business import ai_campaign_v067 as ai_copy


def test_campaign_is_draft_until_merchant_publishes_then_visible_to_customer():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        merchant=Merchant(name='Pilot Bistro',status='active')
        db.add(merchant);db.flush()
        store=Store(merchant_id=merchant.id,name='Central',address='Bucharest',
                    latitude=44.44,longitude=26.10,active=True)
        db.add(store);db.flush()
        program=Program(merchant_id=merchant.id,store_id=store.id,
                        title='Lunch Rewards',description='Stamp every qualifying visit',
                        stamps_required=5,min_purchase_minor=2500,reward_minor=1000,
                        currency='RON',status='published')
        db.add(program);db.commit()
        staff=SimpleNamespace(id='staff1',merchant_id=merchant.id,role='owner')
        proposal=pilot_v05.PromotionIn(program_id=program.id,headline='Lunch gets rewarding',
            message='Earn stamps after merchant-verified visits.',duration_days=14)
        draft=pilot_v05.merchant_create_promo(proposal,staff=staff,db=db)
        assert draft['status']=='draft'
        assert pilot_v05.public_promotions(limit=10,db=db)==[]
        published=pilot_v05.publish_promotion(draft['id'],staff=staff,db=db)
        assert published['status']=='published'
        visible=pilot_v05.public_promotions(limit=10,db=db)
        assert len(visible)==1
        assert visible[0]['id']==draft['id']
        assert visible[0]['program_id']==program.id
        assert visible[0]['reward_minor']==1000
        assert visible[0]['stamps_required']==5
        assert visible[0]['currency']=='RON'
        pilot_v05.unpublish_promotion(draft['id'],staff=staff,db=db)
        assert pilot_v05.public_promotions(limit=10,db=db)==[]


def fake_image():
    buffer=io.BytesIO()
    Image.new('RGB',(64,96),'#cdeee2').save(buffer,'PNG')
    return buffer.getvalue()


def test_provider_image_is_parsed_and_reencoded_to_jpeg(monkeypatch):
    raw=fake_image()
    body=json.dumps({'data':[{'b64_json':base64.b64encode(raw).decode('ascii')}]}).encode()
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,limit):
            assert limit>=len(body)
            return body
    calls=[]
    def fake_open(req,timeout):
        calls.append((req.full_url, timeout,
                      json.loads(req.data.decode('utf-8'))))
        return Response()
    monkeypatch.setattr(artwork,'urlopen',fake_open)
    data=artwork.request_image('Original cafe scene',secret='dummy-token')
    assert calls[0][0]=='https://api.openai.com/v1/images/generations'
    assert calls[0][2]['n']==1
    assert calls[0][2]['output_format']=='png'
    assert calls[0][2]['quality']=='low'
    assert data.startswith(bytes([0xFF,0xD8,0xFF]))
    with Image.open(io.BytesIO(data)) as image:
        assert image.format=='JPEG'


def test_invalid_image_response_fails_cleanly(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,*args):return json.dumps({'data':[{'b64_json':'malformed'}]}).encode()
    monkeypatch.setattr(artwork,'urlopen',lambda *args,**kwargs:Response())
    with pytest.raises(HTTPException) as ex:
        artwork.request_image('Test',secret='not-a-real-secret')
    assert ex.value.status_code==502


def test_ai_artwork_requires_explicit_flag_and_never_publishes(monkeypatch):
    mid='a'*36;pid='b'*36;sid='c'*36
    class DB:
        def get(self,kind,key):
            if kind is Program:return SimpleNamespace(
                id=pid,merchant_id=mid,store_id=sid,status='published',
                title='Coffee loyalty')
            if kind is Merchant:return SimpleNamespace(
                id=mid,name='Local Café',status='active')
            if kind is Store:return SimpleNamespace(
                id=sid,name='Downtown',active=True)
            raise AssertionError('Unexpected DB model')
    staff=SimpleNamespace(id='staff1',role='owner',merchant_id=mid)
    payload=artwork.ArtworkBrief(
       program_id=pid,headline='Your coffee rewards',
       visual_brief='Coffee and breakfast in warm golden sunlight')
    monkeypatch.setenv('OPENAI_API_KEY','unit-test-key')
    monkeypatch.delenv('PRUVS_BUSINESS_AI_IMAGES_ENABLED',raising=False)
    with pytest.raises(HTTPException) as exc:
        artwork.generate_artwork(payload,staff=staff,db=DB())
    assert exc.value.status_code==503
    monkeypatch.setenv('PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED','true')
    monkeypatch.setenv('PRUVS_BUSINESS_AI_IMAGES_ENABLED','true')
    monkeypatch.setattr(pilot_v05,'campaign_schema_ready',lambda db: None)
    monkeypatch.setattr(artwork,'request_image',lambda prompt,secret: b'jpeg-bytes')
    monkeypatch.setattr(artwork,'storage',lambda:(object(),{'PRUVS_CAMPAIGN_R2_BUCKET':'safe'}))
    recorded=[]
    def save(_,cfg,key,data,mime):
        recorded.append((key,data,mime))
        return {'media_key':key,'media_url':'https://assets.example/'+key,
                'media_type':mime}
    monkeypatch.setattr(artwork,'put',save)
    result=artwork.generate_artwork(payload,staff=staff,db=DB())
    assert result['review_required'] is True
    assert result['published'] is False
    assert result['source']=='ai_generated'
    assert recorded[0][0].startswith('campaigns/'+mid+'/')
    assert recorded[0][2]=='image/jpeg'


def test_ai_copy_rejects_nonmerchant_and_requires_published_program(monkeypatch):
    monkeypatch.setenv('PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED','true')
    monkeypatch.setenv('OPENAI_API_KEY','unit-test-key')
    payload=ai_copy.CampaignBrief(
        program_id='1'*36,goal='Bring more customers for lunch')
    with pytest.raises(HTTPException) as exc:
        ai_copy.ai_draft(payload,staff=SimpleNamespace(role='analyst',merchant_id='m1'),
                         db=object())
    assert exc.value.status_code==403
    with pytest.raises(HTTPException) as exc:
        ai_copy.ai_draft(payload,staff=SimpleNamespace(role='owner',merchant_id='m1'),
                         db=SimpleNamespace(get=lambda *args:None))
    assert exc.value.status_code==404


def test_ai_copy_generates_structured_draft_without_publishing(monkeypatch):
    merchant_id='d'*36
    program_id='e'*36
    store_id='f'*36
    monkeypatch.setenv('PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED','true')
    monkeypatch.setenv('OPENAI_API_KEY','unit-test-key')
    monkeypatch.setattr(pilot_v05,'campaign_schema_ready',lambda db: None)
    saved={
      'headline':'Enjoy more of your favourite coffee',
      'message':'Verified coffee purchases earn stamps towards your next reward.',
      'cta':'Join Coffee Rewards',
      'alt_text':'Warm coffee on a sunny cafe counter',
      'visual_brief':'Original cafe portrait with warm light and coffee on a clean table.',
      'motion_storyboard':'Slow pan across a warm cafe counter.',
      'watermark_text':'Pruvs Business',
    }
    fake_reply=json.dumps({'output':[{'content':[
        {'type':'output_text','text':json.dumps(saved)}
    ]}]}).encode('utf-8')
    calls=[]
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,_):return fake_reply
    def open_mock(request,timeout):
        calls.append(json.loads(request.data.decode('utf-8')))
        return Reply()
    monkeypatch.setattr(ai_copy,'urlopen',open_mock)
    class FakeDB:
        def get(self,kind,key):
            if kind is Program:
                return SimpleNamespace(id=program_id,merchant_id=merchant_id,
                    store_id=store_id,status='published',title='Coffee Rewards',
                    description='Five purchases for a reward',currency='RON',
                    min_purchase_minor=2000,stamps_required=5,reward_minor=1000)
            if kind is Merchant:return SimpleNamespace(id=merchant_id,name='Coffee Shop')
            if kind is Store:return SimpleNamespace(id=store_id,name='Central',active=True)
            raise AssertionError('Unexpected model')
    brief=ai_copy.CampaignBrief(program_id=program_id,
        goal='Encourage lunchtime coffee visits')
    response=ai_copy.ai_draft(
        brief,staff=SimpleNamespace(role='owner',merchant_id=merchant_id),
        db=FakeDB())
    assert response['published'] is False
    assert response['review_required'] is True
    assert response['draft']['headline']==saved['headline']
    assert calls[0]['text']['format']['strict'] is True
    assert calls[0]['input']
    assert calls[0]['max_output_tokens']>=700


def test_pre_migration_campaign_status_is_a_controlled_503():
    from sqlalchemy import MetaData,Table,Column,String
    metadata=MetaData()
    Table('loyalty_promotions',metadata,
          Column('id',String,primary_key=True),
          Column('headline',String))
    engine=create_engine('sqlite://')
    metadata.create_all(engine)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            pilot_v05.campaign_schema_ready(db)
        assert exc.value.status_code==503


def test_generated_image_can_be_branded_and_exported_as_png(monkeypatch):
    from business import media_v067
    mid='a'*36
    jpg=io.BytesIO()
    Image.new('RGB',(90,120),'#e4dccf').save(jpg,'JPEG')
    class SourceBody:
        def read(self,maximum):
            assert maximum>0
            return jpg.getvalue()
    class FakeStorage:
        def get_object(self,**kwargs):
            assert kwargs['Bucket']=='pilot-media'
            return {'Body':SourceBody()}
    monkeypatch.setattr(media_v067,'storage',lambda:(
        FakeStorage(),{'PRUVS_CAMPAIGN_R2_BUCKET':'pilot-media'}))
    saved=[]
    def put_mock(client,cfg,key,raw,media_type):
        saved.append((key,raw,media_type))
        return {'media_key':key,'media_type':media_type,
                'media_url':'https://media.example/'+key}
    monkeypatch.setattr(media_v067,'put',put_mock)
    result=media_v067.render_campaign_artwork(
        media_v067.RenderArtworkIn(
            media_key='campaigns/'+mid+'/'+'f'*32+'.jpg',
            format='png',headline='Original local rewards',
            watermark_text='Pruvs Business'
        ),
        staff=SimpleNamespace(id='s1',merchant_id=mid,role='owner'))
    assert result['media_type']=='image/png'
    assert saved[0][0].startswith('campaigns/'+mid+'/')
    with Image.open(io.BytesIO(saved[0][1])) as image:
        assert image.format=='PNG'
        assert image.size==(720,900)
