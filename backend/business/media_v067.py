"""Public campaign media pipeline using durable S3-compatible object storage.

No customer receipt data is ever accepted here. Uploads are re-encoded to
strip EXIF and checked by Pillow; media keys are scoped to authenticated merchant.
"""
from __future__ import annotations
import io, logging, os, re, tempfile, subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat
from .models import Staff
from .security import merchant_actor

router=APIRouter(tags=['Campaign media'])
logger=logging.getLogger(__name__)
MAX_FILE_BYTES=6_000_000
Image.MAX_IMAGE_PIXELS=12_000_000

CAMPAIGN_STORAGE_KEYS = (
    'PRUVS_CAMPAIGN_R2_ENDPOINT_URL',
    'PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID',
    'PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY',
    'PRUVS_CAMPAIGN_R2_BUCKET',
    'PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL',
    'PRUVS_CAMPAIGN_MEDIA_HOSTS',
)


def media_configuration_diagnostics():
    """Return only setting names and error codes; never expose credentials or URLs."""
    values = {name: os.getenv(name, '').strip() for name in CAMPAIGN_STORAGE_KEYS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        return {'ready': False, 'issue': 'missing_settings', 'missing_settings': missing}
    try:
        endpoint = urlsplit(values['PRUVS_CAMPAIGN_R2_ENDPOINT_URL'])
        public = urlsplit(values['PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL'])
    except ValueError:
        return {'ready': False, 'issue': 'invalid_url', 'missing_settings': []}
    if (endpoint.scheme != 'https' or not endpoint.hostname or
            endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
        return {'ready': False, 'issue': 'invalid_r2_endpoint', 'missing_settings': []}
    if (public.scheme != 'https' or not public.hostname or
            public.username or public.password or public.query or public.fragment):
        return {'ready': False, 'issue': 'invalid_public_base_url', 'missing_settings': []}
    allowed = {
        host.strip().lower()
        for host in values['PRUVS_CAMPAIGN_MEDIA_HOSTS'].split(',')
        if host.strip()
    }
    if public.hostname.lower() not in allowed:
        return {'ready': False, 'issue': 'public_hostname_not_allowlisted', 'missing_settings': []}
    return {'ready': True, 'issue': None, 'missing_settings': []}


def bucket_config():
    status = media_configuration_diagnostics()
    if not status['ready']:
        errors = {
            'missing_settings': 'Campaign media storage is not configured',
            'invalid_r2_endpoint': 'Campaign storage endpoint must be HTTPS',
            'invalid_public_base_url': 'Campaign public CDN must use HTTPS',
            'public_hostname_not_allowlisted': 'Campaign public CDN must be on an approved HTTPS host',
            'invalid_url': 'Campaign storage URL is invalid',
        }
        raise HTTPException(503, errors.get(status['issue'], 'Campaign media configuration invalid'))
    return {
        name: os.getenv(name, '').strip()
        for name in CAMPAIGN_STORAGE_KEYS
        if name != 'PRUVS_CAMPAIGN_MEDIA_HOSTS'
    }

def storage():
    cfg=bucket_config()
    try:
        import boto3
        session=boto3.session.Session()
        client=session.client('s3',endpoint_url=cfg['PRUVS_CAMPAIGN_R2_ENDPOINT_URL'],
                aws_access_key_id=cfg['PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID'],
                aws_secret_access_key=cfg['PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY'],
                region_name='auto')
    except ImportError:
        raise HTTPException(503,'Object storage dependency is unavailable') from None
    return client,cfg

def media_url(cfg,key):
    return cfg['PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL'].rstrip('/')+'/'+key

def put(client,cfg,key,data,content_type):
    if len(data)>16_000_000:raise HTTPException(413,'Campaign asset is too large')
    try:
        client.put_object(Bucket=cfg['PRUVS_CAMPAIGN_R2_BUCKET'],Key=key,Body=data,
               ContentType=content_type,CacheControl='public, max-age=31536000, immutable')
    except Exception as exc:
        status=getattr(exc,'response',{}).get('ResponseMetadata',{}).get('HTTPStatusCode')
        logger.warning('Campaign media storage write failed (type=%s, provider_status=%s)',
                       type(exc).__name__, status)
        raise HTTPException(503,'Could not store campaign artwork') from None
    return {'media_url':media_url(cfg,key),'media_key':key,'media_type':content_type}

def read_merchant_campaign_source(staff, media_key):
    """Fetch only a previously uploaded, merchant-owned JPEG for AI image understanding.

    The S3 key is derived from and constrained to the authenticated merchant.
    No arbitrary public URL, bucket key, other merchant asset or receipt is accepted.
    """
    if not isinstance(media_key, str) or not re.fullmatch(
        r'campaigns/' + re.escape(staff.merchant_id) + r'/[a-f0-9]{32}\.jpg',
        media_key,
    ):
        raise HTTPException(403, 'Campaign picture must belong to the signed-in merchant')
    client, cfg = storage()
    try:
        response = client.get_object(
            Bucket=cfg['PRUVS_CAMPAIGN_R2_BUCKET'], Key=media_key
        )
        raw = response['Body'].read(MAX_FILE_BYTES + 1)
    except Exception:
        raise HTTPException(404, 'Uploaded campaign picture is unavailable') from None
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, 'Campaign picture is too large for AI analysis')
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format != 'JPEG':
                raise ValueError('Only normalized campaign JPEGs are accepted')
            picture.verify()
    except (ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, 'Uploaded campaign picture is not valid') from None
    return raw


def require_manager(staff):
    if staff.role not in ('owner','manager'):raise HTTPException(403,'Merchant manager role required')

@router.post('/v1/merchant/promotions/media/upload')
async def upload_campaign_picture(file:UploadFile=File(...),staff:Staff=Depends(merchant_actor)):
    require_manager(staff)
    if file.content_type not in ('image/jpeg','image/png','image/webp'):
        raise HTTPException(415,'Upload a JPEG, PNG or WebP picture')
    raw=await file.read(MAX_FILE_BYTES+1)
    if not raw or len(raw)>MAX_FILE_BYTES:raise HTTPException(413,'Picture must be under 6 MB')
    try:
        picture=Image.open(io.BytesIO(raw))
        if picture.format not in ('JPEG','PNG','WEBP'):raise ValueError('Invalid image')
        picture=ImageOps.exif_transpose(picture).convert('RGB')
        picture.thumbnail((1400,1750),Image.Resampling.LANCZOS)
        buffer=io.BytesIO();picture.save(buffer,format='JPEG',quality=88,optimize=True)
    except (ValueError,OSError,Image.DecompressionBombError):
        raise HTTPException(422,'This picture cannot be processed') from None
    client,cfg=storage()
    key=f'campaigns/{staff.merchant_id}/{uuid4().hex}.jpg'
    return put(client,cfg,key,buffer.getvalue(),'image/jpeg')

class RenderArtworkIn(BaseModel):
    media_key:str=Field(min_length=20,max_length=300)
    format:str=Field(pattern='^(png|gif|mp4)$')
    headline:str=Field(min_length=3,max_length=100)
    watermark_text:str=Field(default='Pruvs Business',min_length=1,max_length=70)

def frame(photo,idx,frames,text,headline):
    w,h=720,900
    # Deterministic Ken Burns move, even when source and target are both 4:5.
    progress=idx/max(1,frames-1)
    zoom=1.07+0.07*progress if frames>1 else 1.0
    scaled=ImageOps.fit(photo,(round(w*zoom),round(h*zoom)),
                        method=Image.Resampling.LANCZOS,centering=(.5,.5))
    dx=scaled.width-w;dy=scaled.height-h
    left=round(dx*(.15+.70*progress))
    top=round(dy*(.20+.60*progress))
    canvas=scaled.crop((left,top,left+w,top+h)).convert('RGB')
    draw=ImageDraw.Draw(canvas)
    # Campaign copy is presented once by the shared Core/Business card overlay.
    try:font=ImageFont.truetype('DejaVuSans-Bold.ttf',22)
    except OSError:font=ImageFont.load_default()
    # Sample the picture behind the watermark and retain its dominant tint while
    # selecting the light/dark treatment that provides the strongest contrast.
    watermark=(text.strip() or 'Pruvs Business')[:55]
    sample=ImageStat.Stat(canvas.crop((20,28,430,96)).resize((1,1))).mean[:3]
    luminance=.2126*sample[0]+.7152*sample[1]+.0722*sample[2]
    if luminance>=142:
        watermark_bg=tuple(round(channel*.28) for channel in sample)
        watermark_fg='#ffffff'
        watermark_outline=(255,255,255)
    else:
        watermark_bg=tuple(round(channel*.18+255*.82) for channel in sample)
        watermark_fg='#0a3128'
        watermark_outline=(9,49,40)
    bounds=draw.textbbox((0,0),watermark.upper(),font=font)
    badge_width=min(660,max(178,bounds[2]-bounds[0]+32))
    draw.rounded_rectangle((24,34,24+badge_width,84),radius=17,fill=watermark_bg,
                           outline=watermark_outline,width=1)
    draw.text((40,46),watermark.upper(),font=font,fill=watermark_fg)
    return canvas

@router.post('/v1/merchant/promotions/media/render')
def render_campaign_artwork(payload:RenderArtworkIn,staff:Staff=Depends(merchant_actor)):
    require_manager(staff)
    if not re.fullmatch(r'campaigns/'+re.escape(staff.merchant_id)+r'/[a-f0-9]{32}\.jpg',payload.media_key):
        raise HTTPException(403,'Artwork must belong to the signed-in merchant')
    client,cfg=storage()
    try:raw=client.get_object(Bucket=cfg['PRUVS_CAMPAIGN_R2_BUCKET'],Key=payload.media_key)['Body'].read(MAX_FILE_BYTES+1)
    except Exception:raise HTTPException(404,'Campaign picture unavailable') from None
    if len(raw)>MAX_FILE_BYTES:raise HTTPException(413,'Campaign picture too large')
    try:photo=Image.open(io.BytesIO(raw)).convert('RGB')
    except (ValueError,OSError,Image.DecompressionBombError):raise HTTPException(422,'Stored image invalid') from None
    frames=1 if payload.format=='png' else 18
    sequence=[frame(photo,i,frames,payload.watermark_text,payload.headline) for i in range(frames)]
    key=f'campaigns/{staff.merchant_id}/{uuid4().hex}.{payload.format}'
    if payload.format=='png':
        buffer=io.BytesIO();sequence[0].save(buffer,format='PNG',optimize=True)
        return put(client,cfg,key,buffer.getvalue(),'image/png')
    if payload.format=='gif':
        buffer=io.BytesIO()
        sequence[0].save(buffer,format='GIF',save_all=True,append_images=sequence[1:],
                 duration=170,loop=0,optimize=True,disposal=2)
        return put(client,cfg,key,buffer.getvalue(),'image/gif')
    try:
        import imageio_ffmpeg
        encoder=imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:raise HTTPException(503,'Video renderer is not configured') from None
    with tempfile.TemporaryDirectory(prefix='pruvs-campaign-') as temp:
        for i,im in enumerate(sequence):im.save(Path(temp)/f'frame_{i:03d}.png',format='PNG')
        out=Path(temp)/'animation.mp4'
        command=[encoder,'-nostdin','-hide_banner','-loglevel','error','-y',
           '-framerate','6','-i',str(Path(temp)/'frame_%03d.png'),
           '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
        try:subprocess.run(command,check=True,timeout=40,capture_output=True)
        except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
            raise HTTPException(503,'Video export is temporarily unavailable') from None
        return put(client,cfg,key,out.read_bytes(),'video/mp4')
