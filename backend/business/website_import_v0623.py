"""Merchant initiated website import: bounded HTTPS, pinned public address, no redirects."""
import http.client,ssl,socket,ipaddress,io
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from PIL import Image,ImageOps
from .models import Staff
from .security import merchant_actor
from .media_v067 import require_manager,storage,put,MAX_FILE_BYTES

router=APIRouter(tags=['Campaign website import'])

def validate_url(url):
    try:
        u=urlsplit(url)
        if len(url)>900 or any(ord(c)<33 or ord(c)>126 for c in url) or '\\' in url or u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443) or u.fragment:
            raise ValueError()
        if u.hostname.endswith('.') or '.' not in u.hostname:raise ValueError()
        try:ipaddress.ip_address(u.hostname)
        except ValueError:pass
        else:raise ValueError()
        return u
    except ValueError:raise HTTPException(422,'Use a public HTTPS website URL without credentials or fragments.') from None

def public_address(host):
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        ips=[ipaddress.ip_address(a[4][0]) for a in addresses]
        if not ips or any(not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip,'ipv4_mapped',None) for ip in ips):raise ValueError()
        return str(ips[0])
    except (OSError,ValueError):raise HTTPException(422,'Website host is not a public address.') from None

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip):
        super().__init__(host,443,timeout=8,context=ssl.create_default_context())
        self.pinned_ip=ip
    def connect(self):
        raw=socket.create_connection((self.pinned_ip,443),self.timeout)
        try:self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception:raw.close();raise

def fetch(url,limit,allowed):
    u=validate_url(url);ip=public_address(u.hostname)
    conn=PinnedHTTPS(u.hostname,ip)
    try:
        conn.request('GET',(u.path or '/')+('?' +u.query if u.query else ''),headers={'User-Agent':'PruvsCampaignStudio/1.0','Accept':', '.join(allowed),'Accept-Encoding':'identity','Connection':'close'})
        r=conn.getresponse()
        if r.status!=200:raise HTTPException(422,'Website did not return a direct public resource. Use the final URL.')
        kind=r.getheader('Content-Type','').split(';')[0].lower()
        if kind not in allowed:raise HTTPException(415,'Unsupported website resource type.')
        data=r.read(limit+1)
        if len(data)>limit:raise HTTPException(413,'Website resource exceeds import limit.')
        return data
    except (OSError,http.client.HTTPException):raise HTTPException(422,'Could not retrieve website resource.') from None
    finally:conn.close()

class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.title='';self.description='';self.images=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='title':self.in_title=True
        if tag=='meta':
            key=(a.get('property') or a.get('name') or '').lower()
            val=a.get('content') or ''
            if key in ('og:image','twitter:image') and val and len(self.images)<40:self.images.insert(0,val)
            if key in ('description','og:description') and val:self.description=val[:500]
        if tag=='img' and a.get('src') and len(self.images)<40:self.images.append(a['src'])
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title=(self.title+data)[:180]

class WebsiteIn(BaseModel):
    url:str=Field(max_length=900)
    rights_confirmed:bool=False

@router.post('/v1/merchant/promotions/website/inspect')
def inspect_website(payload:WebsiteIn,staff:Staff=Depends(merchant_actor)):
    require_manager(staff)
    page=Page();page.feed(fetch(payload.url,1_000_000,['text/html']).decode('utf-8',errors='replace'))
    images=[]
    for value in page.images:
        url=urljoin(payload.url,value)
        try:validate_url(url)
        except HTTPException:continue
        if url not in images:images.append(url)
        if len(images)>=8:break
    return {'title':page.title.strip(),'description':page.description.strip(),'images':images}

@router.post('/v1/merchant/promotions/website/photo')
def import_photo(payload:WebsiteIn,staff:Staff=Depends(merchant_actor)):
    require_manager(staff)
    if not payload.rights_confirmed:raise HTTPException(422,'Confirm permission to use this image.')
    raw=fetch(payload.url,MAX_FILE_BYTES,['image/jpeg','image/png','image/webp'])
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.format not in ('JPEG','PNG','WEBP') or original.width*original.height>12_000_000:raise ValueError()
            picture=ImageOps.exif_transpose(original).convert('RGB')
            picture.thumbnail((1400,1750),Image.Resampling.LANCZOS)
            out=io.BytesIO();picture.save(out,'JPEG',quality=88,optimize=True)
    except (ValueError,OSError,Image.DecompressionBombError):raise HTTPException(422,'Invalid website picture.') from None
    client,cfg=storage()
    return put(client,cfg,f'campaigns/{staff.merchant_id}/{uuid4().hex}.jpg',out.getvalue(),'image/jpeg')
