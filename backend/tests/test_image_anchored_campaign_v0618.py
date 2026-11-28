"""Campaign Studio uses merchant-owned uploaded pictures as the actual campaign subject."""
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from business.ai_campaign_v067 import CampaignBrief, campaign_provider_input
from business import media_v067

ROOT=Path(__file__).resolve().parents[1]


def photo_bytes():
    buffer=io.BytesIO()
    Image.new('RGB',(80,100),(73,116,86)).save(buffer,'JPEG')
    return buffer.getvalue()


def test_creative_brief_supports_only_bounded_image_key():
    model=CampaignBrief(
        program_id='12345678-1234-4234-9234-1234567890ab',
        goal='Bring loyal customers back',
        media_key='campaigns/merchant-one/'+'a'*32+'.jpg',
    )
    assert model.media_key.endswith('.jpg')
    assert CampaignBrief(
        program_id=model.program_id,goal=model.goal
    ).media_key is None
    with pytest.raises(ValidationError):
        CampaignBrief(program_id=model.program_id,goal=model.goal,media_key='x'*301)


def test_multimodal_request_includes_exact_image_with_editable_brief():
    photo=photo_bytes()
    facts={'merchant':'Bistro Central','minimum_purchase_minor':4500,
           'reward_minor':2000,'merchant_creative_brief':'Focus on the pictured coffee.'}
    request=campaign_provider_input(facts,photo)
    assert len(request)==1
    parts=request[0]['content']
    assert parts[0]['type']=='input_text'
    assert json.loads(parts[0]['text'])==facts
    assert parts[1]['type']=='input_image'
    assert parts[1]['image_url']=='data:image/jpeg;base64,'+base64.b64encode(photo).decode('ascii')
    assert campaign_provider_input(facts,None)==json.dumps(facts,ensure_ascii=False)


def test_image_read_is_scoped_to_current_merchant(monkeypatch):
    staff=SimpleNamespace(merchant_id='merchant-one')
    key='campaigns/merchant-one/'+'a'*32+'.jpg'
    foreign_key='campaigns/merchant-two/'+'a'*32+'.jpg'
    calls=[]
    class Store:
        def get_object(self,**kwargs):
            calls.append(kwargs)
            return {'Body':io.BytesIO(photo_bytes())}
    monkeypatch.setattr(media_v067,'storage',lambda:(Store(),{'PRUVS_CAMPAIGN_R2_BUCKET':'campaign-test'}))
    assert media_v067.read_merchant_campaign_source(staff,key)==photo_bytes()
    assert calls==[{'Bucket':'campaign-test','Key':key}]
    with pytest.raises(HTTPException) as exc:
        media_v067.read_merchant_campaign_source(staff,foreign_key)
    assert exc.value.status_code==403
    assert len(calls)==1


def test_image_read_rejects_non_source_asset_and_invalid_jpeg(monkeypatch):
    staff=SimpleNamespace(merchant_id='merchant-one')
    key='campaigns/merchant-one/'+'a'*32+'.jpg'
    for bad in ['https://example.com/photo.jpg',
                'campaigns/merchant-one/'+'a'*32+'.gif',
                'receipts/merchant-one/'+'a'*32+'.jpg',
                'campaigns/merchant-one/../other.jpg']:
        with pytest.raises(HTTPException) as exc:
            media_v067.read_merchant_campaign_source(staff,bad)
        assert exc.value.status_code==403
    class InvalidStore:
        def get_object(self,**kwargs):
            return {'Body':io.BytesIO(b'not a jpeg')}
    monkeypatch.setattr(media_v067,'storage',lambda:(InvalidStore(),{'PRUVS_CAMPAIGN_R2_BUCKET':'campaign-test'}))
    with pytest.raises(HTTPException) as exc:
        media_v067.read_merchant_campaign_source(staff,key)
    assert exc.value.status_code==422


def test_studio_upload_before_generating_and_no_picture_replacement():
    ui=(ROOT/'business_frontend/src/PromotionConsole.jsx').read_text(encoding='utf-8')
    ai=(ROOT/'business/ai_campaign_v067.py').read_text(encoding='utf-8')
    assert ui.index('Main campaign picture and subject')<ui.index('Predefined campaign text · edit before generating')
    assert ui.index('Predefined campaign text · edit before generating')<ui.index('onClick={generateDraft}')
    assert "media_key:imageOrigin==='upload'?artworkKey||null:null" in ui
    assert "imageOrigin==='upload'&&!result.source_image_used" in ui
    assert "if(imageOrigin==='upload')" in ui
    assert 'source_image_used' in ai
    assert "'input':campaign_provider_input(facts,source_image)" in ai
    assert "visible main product, food, object or scene" in ai
    assert 'setRenderedSignature(renderSignature)' in ui
    assert "imageOrigin==='upload'?'Replace main picture':'Upload main campaign picture'" in ui
