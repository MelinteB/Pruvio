"""Public campaign media pipeline using durable S3-compatible object storage.

No customer receipt data is ever accepted here. Uploads are re-encoded to
strip EXIF and checked by Pillow; media keys are scoped to authenticated merchant.
"""
from __future__ import annotations
import io, logging, os, re, tempfile, subprocess, socket, ipaddress, http.client, ssl
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urljoin, urlunsplit
from html.parser import HTMLParser
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat
from sqlalchemy.orm import Session
from .db import get_db
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
    legacy = r'campaigns/' + re.escape(staff.merchant_id) + r'/[a-f0-9]{32}\.jpg'
    managed = r'campaigns/' + re.escape(staff.merchant_id) + r'/sources/[a-f0-9]{32}\.jpg'
    if not isinstance(media_key, str) or not re.fullmatch(f'(?:{legacy}|{managed})', media_key):
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
async def upload_campaign_picture(file:UploadFile=File(...),staff:Staff=Depends(merchant_actor),
                                 db:Session=Depends(get_db)):
    require_manager(staff)
    from .media_assets_v0725 import media_registry_ready, register_media
    if not media_registry_ready(db):
        raise HTTPException(503,'Campaign media registry is not ready. Apply the reviewed additive migration.')
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
    key=f'campaigns/{staff.merchant_id}/sources/{uuid4().hex}.jpg'
    register_media(db,staff.merchant_id,key,'source')
    client,cfg=storage()
    return put(client,cfg,key,buffer.getvalue(),'image/jpeg')

class RenderArtworkIn(BaseModel):
    media_key:str=Field(min_length=20,max_length=300)
    format:str=Field(pattern='^(png|gif|mp4)$')
    headline:str=Field(min_length=3,max_length=100)
    watermark_text:str=Field(default='Pruvs Business',min_length=1,max_length=70)


class GalleryStoryIn(BaseModel):
    gallery_keys:list[str]=Field(min_length=2,max_length=5)
    headline:str=Field(min_length=5,max_length=100)
    message:str=Field(min_length=10,max_length=500)
    cta:str=Field(min_length=2,max_length=42)
    watermark_text:str=Field(default='Pruvs Business',min_length=1,max_length=70)
    motion_storyboard:str=Field(default='',max_length=400)
    format:str=Field(default='mp4',pattern='^(gif|mp4)$')


class WebsiteCandidatesIn(BaseModel):
    website_url:str=Field(min_length=8,max_length=500)


class WebsiteImageImportIn(WebsiteCandidatesIn):
    image_url:str=Field(min_length=8,max_length=1000)


class _ImageLinks(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs={key.lower():value for key,value in attrs if key and value}
        if tag.lower()=='meta' and (attrs.get('property','').lower()=='og:image' or attrs.get('name','').lower() in ('twitter:image','twitter:image:src')):
            self.links.append(attrs.get('content',''))
        if tag.lower()=='img' and attrs.get('src'):self.links.append(attrs['src'])
        if tag.lower()=='img' and attrs.get('srcset'):
            self.links.extend(part.strip().split()[0] for part in attrs['srcset'].split(',') if part.strip())


def _checked_https_url(raw):
    try:parsed=urlsplit(str(raw).strip())
    except ValueError:raise HTTPException(422,'Enter a valid public HTTPS restaurant website') from None
    try:port=parsed.port
    except ValueError:raise HTTPException(422,'Enter a valid public HTTPS restaurant website') from None
    if (parsed.scheme.lower()!='https' or not parsed.hostname or parsed.username or parsed.password
            or port not in (None,443) or parsed.fragment):
        raise HTTPException(422,'Only public HTTPS websites and images are supported')
    try:host=parsed.hostname.encode('idna').decode('ascii').lower().rstrip('.')
    except UnicodeError:raise HTTPException(422,'Enter a valid public HTTPS restaurant website') from None
    if not host or host=='localhost' or host.endswith('.localhost') or host.endswith('.local'):
        raise HTTPException(422,'Private or local website addresses are not allowed')
    try:ipaddress.ip_address(host)
    except ValueError:pass
    else:raise HTTPException(422,'Use the restaurant website hostname instead of a direct IP address')
    try:addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except OSError:raise HTTPException(422,'The restaurant website could not be resolved') from None
    ips={ipaddress.ip_address(item[4][0]) for item in addresses}
    if not ips or any(not ip.is_global for ip in ips):
        raise HTTPException(422,'Private or local website addresses are not allowed')
    return parsed,host,sorted(ips,key=lambda ip:(ip.version,int(ip)))[0].compressed


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,host,ip,**kwargs):super().__init__(host,**kwargs);self._pinned_ip=ip
    def connect(self):
        sock=socket.create_connection((self._pinned_ip,self.port),self.timeout,self.source_address)
        self.sock=self._context.wrap_socket(sock,server_hostname=self.host)


def _fetch_public_https(raw,*,allowed_types,max_bytes):
    current=str(raw)
    for redirects in range(4):
        parsed,host,ip=_checked_https_url(current)
        conn=_PinnedHTTPSConnection(host,ip,timeout=8,context=ssl.create_default_context())
        path=urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
        try:
            conn.request('GET',path,headers={'Host':host,'User-Agent':'Pruvs-Campaign-Image-Importer/1.0','Accept':', '.join(allowed_types)})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location');response.read(1024);conn.close()
                if not location or redirects>=3:raise HTTPException(422,'Restaurant website redirected too many times')
                current=urljoin(current,location);continue
            if response.status!=200:raise HTTPException(422,'Restaurant website did not provide the selected content')
            content_type=response.getheader('Content-Type','').split(';')[0].strip().lower()
            if content_type not in allowed_types:raise HTTPException(415,'The selected website resource has an unsupported content type')
            length=response.getheader('Content-Length')
            if length and (not length.isdigit() or int(length)>max_bytes):raise HTTPException(413,'Website content exceeds the import size limit')
            data=response.read(max_bytes+1)
            if len(data)>max_bytes:raise HTTPException(413,'Website content exceeds the import size limit')
            return data,content_type,current
        finally:conn.close()
    raise HTTPException(422,'Restaurant website redirected too many times')


def _website_candidates(website_url):
    html,_,final_url=_fetch_public_https(website_url,allowed_types=('text/html','application/xhtml+xml'),max_bytes=2_000_000)
    try:parser=_ImageLinks();parser.feed(html.decode('utf-8','replace'))
    except Exception:raise HTTPException(422,'Could not read the restaurant website image links') from None
    result=[];seen=set()
    for link in parser.links:
        if not link:continue
        candidate=urljoin(final_url,link.strip())
        try:parsed,host,_=_checked_https_url(candidate)
        except HTTPException:continue
        normalized=urlunsplit(('https',host,parsed.path or '/',parsed.query,''))
        if normalized in seen:continue
        seen.add(normalized);result.append({'url':normalized,'host':host})
        if len(result)>=20:break
    return final_url,result


@router.post('/v1/merchant/promotions/media/website-candidates')
def website_image_candidates(payload:WebsiteCandidatesIn,staff:Staff=Depends(merchant_actor)):
    require_manager(staff)
    final_url,candidates=_website_candidates(payload.website_url)
    return {'website_url':final_url,'candidates':candidates,'notice':'Review each image and confirm that your business may use it before importing.'}


@router.post('/v1/merchant/promotions/media/import-website-image')
def import_website_image(payload:WebsiteImageImportIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    require_manager(staff)
    if payload.image_url not in {item['url'] for item in _website_candidates(payload.website_url)[1]}:
        raise HTTPException(422,'Choose an image found on the restaurant website first')
    raw,content_type,_=_fetch_public_https(payload.image_url,allowed_types=('image/jpeg','image/png','image/webp'),max_bytes=MAX_FILE_BYTES)
    try:
        picture=Image.open(io.BytesIO(raw))
        if picture.format not in ('JPEG','PNG','WEBP'):raise ValueError('Invalid image')
        picture=ImageOps.exif_transpose(picture).convert('RGB')
        picture.thumbnail((1400,1750),Image.Resampling.LANCZOS)
        buffer=io.BytesIO();picture.save(buffer,format='JPEG',quality=88,optimize=True)
    except (ValueError,OSError,Image.DecompressionBombError):raise HTTPException(422,'Selected website image cannot be processed') from None
    from .media_assets_v0725 import media_registry_ready,register_media
    if not media_registry_ready(db):raise HTTPException(503,'Campaign media registry is not ready. Apply the reviewed additive migration.')
    key=f'campaigns/{staff.merchant_id}/sources/{uuid4().hex}.jpg'
    register_media(db,staff.merchant_id,key,'source')
    client,cfg=storage()
    return put(client,cfg,key,buffer.getvalue(),'image/jpeg')


def _story_caption(text):
    clean=' '.join(str(text or '').split()).strip()
    return clean[:72]


def _story_frame(photo, index, frame_count, caption):
    w,h=480,600
    progress=index/max(1,frame_count-1)
    zoom=1.08+0.12*progress
    source=ImageOps.fit(photo,(round(w*zoom),round(h*zoom)),method=Image.Resampling.LANCZOS,
                        centering=(.35+.3*progress,.65-.3*progress))
    dx,dy=source.width-w,source.height-h
    x=round(dx*progress);y=round(dy*(1-progress))
    canvas=source.crop((x,y,x+w,y+h)).convert('RGB')
    draw=ImageDraw.Draw(canvas,'RGBA')
    try:font=ImageFont.truetype('DejaVuSans-Bold.ttf',24)
    except OSError:font=ImageFont.load_default()
    draw.rounded_rectangle((24,440,456,570),radius=22,fill=(5,28,24,190))
    lines=[];line=''
    for word in caption.split():
        candidate=(line+' '+word).strip()
        if draw.textlength(candidate,font=font)>372 and line:
            lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    for row,text in enumerate(lines[:3]):
        draw.text((40,458+row*31),text,font=font,fill=(255,255,255,255),stroke_width=1,stroke_fill=(0,0,0,120))
    return canvas


@router.post('/v1/merchant/promotions/media/story')
def render_gallery_story(payload:GalleryStoryIn,staff:Staff=Depends(merchant_actor),db:Session=Depends(get_db)):
    """Create a short three-beat transition story from merchant-owned gallery photos."""
    require_manager(staff)
    if len(set(payload.gallery_keys))!=len(payload.gallery_keys):
        raise HTTPException(422,'Choose each gallery photo only once')
    if len(payload.gallery_keys)<2:
        raise HTTPException(422,'Choose at least two campaign photos for a story')
    from .media_assets_v0725 import media_registry_ready,register_media
    if not media_registry_ready(db):
        raise HTTPException(503,'Campaign media registry is not ready. Apply the reviewed additive migration.')
    photos=[]
    for key in payload.gallery_keys:
        raw=read_merchant_campaign_source(staff,key)
        try:photos.append(Image.open(io.BytesIO(raw)).convert('RGB'))
        except (ValueError,OSError,Image.DecompressionBombError):
            raise HTTPException(422,'A selected campaign photo is invalid') from None
    ai_beats=[_story_caption(part) for part in re.split(r'(?:\s*→\s*|\s*->\s*|[;\n]+|\.\s+)',payload.motion_storyboard) if _story_caption(part)]
    beats=ai_beats[:3] if len(ai_beats)>=3 else [
        _story_caption(payload.headline),_story_caption(payload.message),_story_caption(payload.cta)]
    beat_count=3;frames_per_beat=18;fade_frames=4;sequence=[]
    for beat in range(beat_count):
        photo=photos[round(beat*(len(photos)-1)/(beat_count-1))]
        scene=[_story_frame(photo,i,frames_per_beat,beats[beat]) for i in range(frames_per_beat)]
        if sequence:
            prior=sequence[-fade_frames:]
            for n,old in enumerate(prior):
                alpha=(n+1)/(fade_frames+1)
                sequence[-fade_frames+n]=Image.blend(old,scene[n],alpha)
            sequence.extend(scene[fade_frames:])
        else:sequence.extend(scene)
    client,cfg=storage()
    key=f'campaigns/{staff.merchant_id}/renders/{uuid4().hex}.{payload.format}'
    if payload.format=='gif':
        output=io.BytesIO();sequence[0].save(output,format='GIF',save_all=True,append_images=sequence[1:],
            duration=167,loop=0,optimize=True,disposal=2)
        media_type='image/gif';data=output.getvalue()
    else:
        try:
            import imageio_ffmpeg
            encoder=imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:raise HTTPException(503,'Video renderer is not configured') from None
        with tempfile.TemporaryDirectory(prefix='pruvs-campaign-story-') as temp:
            for i,im in enumerate(sequence):im.save(Path(temp)/f'frame_{i:03d}.jpg',format='JPEG',quality=82)
            out=Path(temp)/'story.mp4'
            command=[encoder,'-nostdin','-hide_banner','-loglevel','error','-y','-framerate','6',
                '-i',str(Path(temp)/'frame_%03d.jpg'),'-c:v','libx264','-pix_fmt','yuv420p',
                '-movflags','+faststart',str(out)]
            try:subprocess.run(command,check=True,timeout=45,capture_output=True)
            except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired):
                raise HTTPException(503,'Campaign story export is temporarily unavailable') from None
            data=out.read_bytes();media_type='video/mp4'
    if len(data)>16_000_000:raise HTTPException(413,'Generated campaign story is too large')
    register_media(db,staff.merchant_id,key,'render')
    try:return put(client,cfg,key,data,media_type)
    except HTTPException:
        db.rollback()
        raise

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
def render_campaign_artwork(payload:RenderArtworkIn,staff:Staff=Depends(merchant_actor),
                            db:Session=Depends(get_db)):
    require_manager(staff)
    from .media_assets_v0725 import media_registry_ready, register_media
    if not media_registry_ready(db):
        raise HTTPException(503,'Campaign media registry is not ready. Apply the reviewed additive migration.')
    # The endpoint may render a new version from either an older source key or a
    # v0.6.25 source key. Render outputs are separately tracked for safe cleanup.
    raw=read_merchant_campaign_source(staff,payload.media_key)
    client,cfg=storage()
    try:photo=Image.open(io.BytesIO(raw)).convert('RGB')
    except (ValueError,OSError,Image.DecompressionBombError):raise HTTPException(422,'Stored image invalid') from None
    frames=1 if payload.format=='png' else 18
    sequence=[frame(photo,i,frames,payload.watermark_text,payload.headline) for i in range(frames)]
    key=f'campaigns/{staff.merchant_id}/renders/{uuid4().hex}.{payload.format}'
    register_media(db,staff.merchant_id,key,'render')
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
