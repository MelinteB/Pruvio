import pytest
from PIL import Image
from fastapi import HTTPException
from business.website_import_v0623 import validate_url,public_address
from business.media_v067 import render_sequence

def test_website_url_restrictions():
    for url in ('http://example.org','https://127.0.0.1','https://user@example.org','https://example.org:444','https://localhost'):
        with pytest.raises(HTTPException):validate_url(url)
    assert validate_url('https://example.org/menu').hostname=='example.org'

def test_private_dns_rejected(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.0.0.1',443))])
    with pytest.raises(HTTPException):public_address('example.org')

def test_slideshow_has_distinct_photos_and_frames():
    photos=[Image.new('RGB',(720,900),c) for c in ['red','blue']]
    frames=render_sequence(photos,'mp4','Pruvs','Campaign')
    assert len(frames)==18
    assert frames[0].getpixel((360,400))!=frames[-1].getpixel((360,400))
    assert len(render_sequence(photos,'png','Pruvs','Campaign'))==1
