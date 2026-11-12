"""Public campaign media pipeline using durable S3-compatible object storage.

No customer receipt data is ever accepted here. Uploads are re-encoded to
strip EXIF and checked by Pillow; media keys are scoped to authenticated merchant.
"""
from __future__ import annotations
import io, os, re, tempfile, subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageOps
from .models import Staff
from .security import merchant_actor

router=APIRouter(tags=['Campaign media'])
MAX_FILE_BYTES=6_000_000
Image.MAX_IMAGE_PIXELS=12_000_000

def bucket_config():
    keys=['PRUVS_CAMPAIGN_R2_ENDPOINT_URL','PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID',
          'PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY','PRUVS_CAMPAIGN_R2_BUCKET',
          'PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL']
    values={k:os.getenv(k,'').strip() for k in keys}
    if not all(values.values()):
        raise HTTPException(503,'Campaign media storage is not configured')
    endpoint=urlsplit(values[keys[0]])
    public=urlsplit(values[keys[4]])
    allowed={v.strip().lower() for v in os.getenv('PRUVS_CAMPAIGN_MEDIA_HOSTS','').split(',') if v.strip()}
    if endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        raise HTTPException(503,'Campaign storage endpoint must be HTTPS')
    if public.scheme!='https' or not public.hostname or public.hostname.lower() not in allowed or public.username or public.password or public.query or public.fragment:
        raise HTTPException(503,'Campaign public CDN must be on an approved HTTPS host')
    return values

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
    except Exception:
        raise HTTPException(503,'Could not store campaign artwork') from None
    return {'media_url':media_url(cfg,key),'media_key':key,'media_type':content_type}

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
    photo=ImageOps.fit(photo,(w,h),method=Image.Resampling.LANCZOS,
         centering=(.5+.015*(idx/max(1,frames-1)-.5),.5))
    canvas=photo.copy().convert('RGB');draw=ImageDraw.Draw(canvas)
    draw.rectangle((0,755,720,900),fill='#092a24')
    draw.rectangle((24,36,205,80),fill='#e5fff2')
    try:font=ImageFont.truetype('DejaVuSans-Bold.ttf',22)
    except OSError:font=ImageFont.load_default()
    draw.text((36,43),'PRUVS BUSINESS',font=font,fill='#075f42')
    draw.text((26,780),headline[:48],font=font,fill='#ffffff')
    draw.text((26,844),text[:55],font=font,fill='#8bebc4')
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
