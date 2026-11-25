import io
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from PIL import Image
from business.media_v067 import campaign_source_keys,photo_collage
from business.ai_campaign_v067 import campaign_provider_input,CampaignBrief

def test_multiple_sources_are_bounded_and_merchant_owned():
    staff=SimpleNamespace(merchant_id='merchant')
    keys=['campaigns/merchant/'+c*32+'.jpg' for c in 'abcde']
    assert campaign_source_keys(staff,keys[0],keys)==keys
    for invalid in [[keys[0]]*2,keys+[keys[0]]]:
        with pytest.raises(HTTPException):campaign_source_keys(staff,keys[0],invalid)
    with pytest.raises(HTTPException):campaign_source_keys(staff,keys[0],[keys[0],'campaigns/other/'+'a'*32+'.jpg'])

def test_all_images_sent_to_ai_in_main_first_order():
    parts=campaign_provider_input({'uploaded_photo_count':3},[b'first',b'second',b'third'])[0]['content']
    assert [p['image_url'] for p in parts[1:]]==['data:image/jpeg;base64,Zmlyc3Q=','data:image/jpeg;base64,c2Vjb25k','data:image/jpeg;base64,dGhpcmQ=']

def test_collage_preserves_all_source_images():
    photos=[Image.new('RGB',(90,90),c) for c in ['red','green','blue']]
    result=photo_collage(photos)
    assert result.size==(720,900)
    assert result.getpixel((360,240))==(255,0,0)
    assert result.getpixel((180,620))==(0,128,0)
    assert result.getpixel((540,620))==(0,0,255)
