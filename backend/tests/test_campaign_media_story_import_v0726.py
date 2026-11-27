"""URL import is public-HTTPS only; gallery stories are real multi-scene media."""
import os

os.environ.setdefault('BUSINESS_JWT_SECRET','test-jwt-secret-'*4)
os.environ.setdefault('PRUVS_BRIDGE_SECRET','test-bridge-secret-'*4)
os.environ.setdefault('APP_ENV','testing')

import pytest
from fastapi import HTTPException
from PIL import Image

from business import media_v067


def _dns(ip):
    return [(2,1,6,'',(ip,443))]


def test_website_import_refuses_private_dns_targets(monkeypatch):
    monkeypatch.setattr(media_v067.socket,'getaddrinfo',lambda *args,**kwargs:_dns('127.0.0.1'))
    with pytest.raises(HTTPException) as error:
        media_v067._checked_https_url('https://restaurant.example/menu')
    assert error.value.status_code==422
    assert 'Private or local' in error.value.detail


def test_website_import_requires_https_and_only_accepts_allowed_ports():
    with pytest.raises(HTTPException):media_v067._checked_https_url('http://restaurant.example')
    with pytest.raises(HTTPException):media_v067._checked_https_url('https://restaurant.example:8443')


def test_storyboard_frame_uses_campaign_caption_and_vertical_story_canvas():
    photo=Image.new('RGB',(800,500),(190,90,40))
    frame=media_v067._story_frame(photo,3,18,'Come back for your next favorite meal')
    assert frame.size==(480,600)
    assert frame.mode=='RGB'


def test_website_candidates_extract_public_image_sources(monkeypatch):
    page=b'<meta property="og:image" content="/cover.jpg"><img src="https://cdn.example/photo.png">'
    monkeypatch.setattr(media_v067,'_fetch_public_https',lambda *a,**k:(page,'text/html','https://bistro.example/menu'))
    monkeypatch.setattr(media_v067,'_checked_https_url',lambda raw:(media_v067.urlsplit(raw),media_v067.urlsplit(raw).hostname,'93.184.216.34'))
    final,candidates=media_v067._website_candidates('https://bistro.example')
    assert final=='https://bistro.example/menu'
    assert [item['url'] for item in candidates]==[
        'https://bistro.example/cover.jpg','https://cdn.example/photo.png']
