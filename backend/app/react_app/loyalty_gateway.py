"""Server-only Pruvs -> Pruvs Business pilot gateway.

The Business bridge secret and session JWT never leave this backend.  This module
intentionally does not implement receipt proof: OCR-only merchant naming cannot
safely establish membership in a registered merchant/store.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib import error, parse, request
from fastapi import HTTPException


def _base64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def enabled():
    return os.getenv('PRUVS_LOYALTY_ENABLED', '').lower() == 'true'


def config():
    if not enabled():
        raise HTTPException(503, 'Pruvs Rewards is not enabled in this environment.')
    secret = os.getenv('PRUVS_BRIDGE_SECRET', '')
    if len(secret) < 32:
        raise HTTPException(503, 'Pruvs Rewards bridge is not configured.')
    combined = os.getenv('PRUVS_PLATFORM_COMBINED_STAGING', '').lower() == 'true'
    if combined:
        # Fixed loopback address + Render-provided port. No user-supplied URLs.
        port = os.getenv('PORT', '').strip()
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            raise HTTPException(503, 'Local Business route is not configured.')
        raw = 'http://127.0.0.1:' + port + '/business'
    else:
    raw = os.getenv('PRUVS_BUSINESS_API_URL', '').strip().rstrip('/')
    p = parse.urlsplit(raw)
    is_https = p.scheme == 'https'
    combined_local = (combined and p.scheme == 'http' and p.hostname == '127.0.0.1' and p.path == '/business' and p.port == int(port))
    local_dev = (p.scheme == 'http' and p.hostname in ('127.0.0.1', 'localhost')
                 and os.getenv('PRUVS_LOYALTY_LOCAL_HTTP', '').lower() == 'true'
                 and os.getenv('APP_ENV', 'production').lower() != 'production')
    if not (is_https or local_dev or combined_local) or not p.hostname or p.username or p.password or (p.path not in ('', '/') and not combined_local) or p.query or p.fragment:
        raise HTTPException(503, 'Pruvs Business API is not configured securely.')
    return raw, secret


def pseudonym(secret, kind, value):
    if value is None or not str(value):
        raise ValueError('A server-side account identifier is required.')
    return hmac.new(secret.encode('utf-8'), f'{kind}:{value}'.encode('utf-8'), hashlib.sha256).hexdigest()


def customer_token(secret, user_id, now=None):
    """HS256 JWT compatible with existing Business customer_actor()."""
    now = int(time.time()) if now is None else int(now)
    head = {'alg':'HS256', 'typ':'JWT'}
    body = {'iss':'pruvs-core', 'aud':'pruvs-business', 'typ':'customer_session',
            'sub':pseudonym(secret, 'customer-v1', user_id), 'iat':now, 'exp':now + 900,
            'jti':secrets.token_hex(16)}
    a = _base64url(json.dumps(head, separators=(',', ':')).encode())
    b = _base64url(json.dumps(body, separators=(',', ':')).encode())
    payload = f'{a}.{b}'
    sig = _base64url(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return payload + '.' + sig


def call_business(path, *, method='GET', user_id=None, params=None, body=None):
    """Only sends fixed server-authored paths to the configured Business service.

    Network failures do not disclose URLs, credentials, or upstream diagnostics.
    Mutating requests are never retried to avoid duplicate operations.
    """
    base, secret = config()
    valid_prefixes = ('/v1/discover', '/v1/promotions', '/v1/customer/')
    if not isinstance(path, str) or not any(path == p or path.startswith(p) for p in valid_prefixes):
        raise ValueError('Unsupported Business API operation')
    if method not in ('GET', 'POST'):
        raise ValueError('Unsupported request method')
    if user_id is None and path.startswith('/v1/customer/'):
        raise HTTPException(401, 'Sign in to continue.')
    qs = parse.urlencode(params) if params else ''
    url = base + path + (('?' + qs) if qs else '')
    headers = {'Accept':'application/json', 'User-Agent':'Pruvs-Loyalty-Bridge/0.4'}
    if user_id is not None:
        headers['Authorization'] = 'Bearer ' + customer_token(secret, user_id)
    if method == 'POST':
        headers['Content-Type'] = 'application/json'
    req = request.Request(url, method=method, headers=headers,
                          data=json.dumps(body if body is not None else {},separators=(',',':')).encode('utf-8') if method == 'POST' else None)
    try:
        with request.urlopen(req, timeout=9) as res:
            if res.status not in (200, 201):
                raise HTTPException(502, 'Unexpected response from loyalty service.')
            content = res.read(262145)
            if len(content) > 262144:
                raise HTTPException(502, 'Loyalty service response too large.')
            return json.loads(content)
    except error.HTTPError as exc:
        if exc.code in (400, 401, 403, 404, 409, 422, 429):
            # Sanitized messages; do not reflect upstream error bodies.
            messages = {400:'Invalid loyalty request.',401:'Loyalty session expired. Try again.',
                        403:'This loyalty action is not permitted.',404:'Loyalty record not available.',
                        409:'This loyalty action has already been completed or cannot proceed.',
                        422:'This loyalty request is not eligible.',429:'Too many loyalty requests. Try again later.'}
            raise HTTPException(exc.code, messages[exc.code]) from None
        raise HTTPException(503, 'Loyalty service is temporarily unavailable.') from None
    except HTTPException:
        raise
    except (error.URLError, TimeoutError, OSError, ValueError, UnicodeError):
        raise HTTPException(503, 'Loyalty service is temporarily unavailable.') from None


def receipt_proof(secret, user_id, case_id, store_id, amount_minor, currency):
    """Short-lived signed statement about an owned Pruvs receipt; code verified by Business."""
    now=int(time.time())
    body={'iss':'pruvs-core','aud':'pruvs-business','typ':'receipt_proof',
          'sub':pseudonym(secret,'customer-v1',user_id),
          'receipt_id':pseudonym(secret,'receipt-v1',f'{user_id}:{case_id}'),
          'store_id':store_id,'amount_minor':amount_minor,'currency':currency,
          'iat':now,'exp':now+300,'jti':secrets.token_hex(16)}
    a=_base64url(json.dumps({'alg':'HS256','typ':'JWT'},separators=(',',':')).encode())
    b=_base64url(json.dumps(body,separators=(',',':')).encode())
    sig=_base64url(hmac.new(secret.encode(),(a+'.'+b).encode(),hashlib.sha256).digest())
    return a+'.'+b+'.'+sig
