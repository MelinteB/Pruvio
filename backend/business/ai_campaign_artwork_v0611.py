"""Merchant-controlled AI campaign artwork for Pruvs Business v0.6.11.

AI output is never published automatically. Only authenticated merchants with
a published program can create a generated source image. A separate review,
render and publish action is still required.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from .db import get_db
from .models import Merchant, Program, Staff, Store
from .security import merchant_actor
from .media_v067 import storage, put

router = APIRouter(tags=['AI campaign artwork'])
MAX_GENERATED_BYTES = 12_000_000


def ai_images_enabled():
    return (os.getenv('PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED', 'false').lower() == 'true'
            and os.getenv('PRUVS_BUSINESS_AI_IMAGES_ENABLED', 'false').lower() == 'true')


class ArtworkBrief(BaseModel):
    program_id: str = Field(min_length=36, max_length=36)
    headline: str = Field(min_length=5, max_length=100)
    visual_brief: str = Field(min_length=12, max_length=300)


def image_prompt(merchant, store, program, payload: ArtworkBrief):
    """Only campaign-safe, scoped facts from the server are authoritative."""
    return (
        'Produce original, tasteful commercial campaign background photography or '
        'illustration for a local merchant loyalty offer. Portrait mobile image 2:3, '
        'premium composition, lively but clean, excellent contrast, no logos, text, '
        'letters, QR codes, prices, currency symbols, reward claims or identifiable people. '
        'Leave generous clear space at top and bottom for the app to add verified copy '
        'and the Pruvs watermark. Do not imitate copyrighted characters, famous brands '
        'or existing advertising campaigns.\n'
        'Merchant: ' + merchant.name[:180] + '\n'
        'Location: ' + store.name[:180] + '\n'
        'Approved loyalty program: ' + program.title[:180] + '\n'
        'Merchant-reviewed headline (not to render as text): ' + payload.headline + '\n'
        'Visual creative direction: ' + payload.visual_brief
    )


def request_image(prompt, secret):
    """One provider call. No retries, ensuring unexpected costs are not multiplied."""
    body = {
        'model': os.getenv('PRUVS_CAMPAIGN_AI_IMAGE_MODEL', 'gpt-image-2'),
        'prompt': prompt,
        'size': '1024x1536',
        'quality': 'low',
        'output_format': 'png',
        'n': 1,
    }
    req = Request(
        'https://api.openai.com/v1/images/generations',
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        method='POST',
        headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'},
    )
    try:
        with urlopen(req, timeout=105) as response:
            payload = json.loads(response.read(24_000_001))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        raise HTTPException(502, 'AI campaign image could not be generated. Review provider access and account limits.') from None
    try:
        encoded = payload['data'][0]['b64_json']
        if not isinstance(encoded, str) or len(encoded) > 17_000_000:
            raise ValueError('Invalid output size')
        raw = base64.b64decode(encoded, validate=True)
        if not 0 < len(raw) <= MAX_GENERATED_BYTES:
            raise ValueError('Invalid image size')
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format not in ('PNG', 'JPEG', 'WEBP'):
                raise ValueError('Invalid image format')
            if picture.width * picture.height > 20_000_000:
                raise ValueError('Image dimensions exceed limit')
            image = ImageOps.exif_transpose(picture).convert('RGB')
            image.thumbnail((1400, 1750), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=87, optimize=True)
        return buffer.getvalue()
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error,
            UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise HTTPException(502, 'AI provider returned an invalid campaign image.') from None


@router.post('/v1/merchant/promotions/ai-artwork')
def generate_artwork(payload: ArtworkBrief, staff: Staff = Depends(merchant_actor),
                     db: Session = Depends(get_db)):
    if staff.role not in ('owner', 'manager'):
        raise HTTPException(403, 'Merchant manager role required')
    if not ai_images_enabled():
        raise HTTPException(503, 'AI artwork generation is disabled on this service.')
    secret = os.getenv('OPENAI_API_KEY', '').strip()
    if not secret:
        raise HTTPException(503, 'AI image provider is not configured on the server.')
    program = db.get(Program, payload.program_id)
    if not program or program.merchant_id != staff.merchant_id or program.status != 'published':
        raise HTTPException(404, 'Select a published loyalty program owned by this merchant.')
    merchant = db.get(Merchant, staff.merchant_id)
    store = db.get(Store, program.store_id)
    if not merchant or merchant.status != 'active' or not store or not store.active:
        raise HTTPException(409, 'Active merchant and store are required.')

    # Check media credentials and allowlisted CDN before incurring provider costs.
    client, cfg = storage()
    raw = request_image(image_prompt(merchant, store, program, payload), secret)
    key = f'campaigns/{staff.merchant_id}/{uuid4().hex}.jpg'
    saved = put(client, cfg, key, raw, 'image/jpeg')
    return {**saved, 'source': 'ai_generated', 'published': False,
            'review_required': True,
            'note': 'Review artwork, render branded asset, save as draft, then publish manually.'}


@router.get('/v1/merchant/promotions/ai-readiness')
def ai_readiness(staff: Staff = Depends(merchant_actor)):
    if staff.role not in ('owner', 'manager'):
        raise HTTPException(403, 'Merchant manager role required')
    ai = os.getenv('PRUVS_BUSINESS_AI_CAMPAIGNS_ENABLED', 'false').lower() == 'true'
    has_key = bool(os.getenv('OPENAI_API_KEY', '').strip())
    image = ai_images_enabled()
    return {
        'copy_ready': ai and has_key,
        'artwork_ready': image and has_key and all(os.getenv(key, '').strip() for key in (
            'PRUVS_CAMPAIGN_R2_ENDPOINT_URL', 'PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID',
            'PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY', 'PRUVS_CAMPAIGN_R2_BUCKET',
            'PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL', 'PRUVS_CAMPAIGN_MEDIA_HOSTS')),
        'message': 'AI generation is billed by the configured provider; publishing always requires merchant review.',
    }
