"""Public deletion instructions and authenticated Meta deauthorization callback."""
import base64
import hashlib
import hmac
import json
import os
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from app.db.database import get_db
from app.models.social_identity import SocialAccount
from app.react_app.auth import revoke_user

router=APIRouter()

def _decode(s):
    return base64.b64decode(s+"="*(-len(s)%4),altchars=b"-_",validate=True)

def verify_signed_request(raw, secret):
    try:
        if not secret or len(raw)>8192:raise ValueError()
        sig,payload=raw.split(".",1)
        expected=hmac.new(secret.encode(),payload.encode(),hashlib.sha256).digest()
        if not hmac.compare_digest(_decode(sig),expected):raise ValueError()
        body=json.loads(_decode(payload))
        if body.get("algorithm")!="HMAC-SHA256":raise ValueError()
        issued=int(body["issued_at"])
        if not -60 <= time.time()-issued <= 86400:raise ValueError()
        subject=str(body["user_id"])
        if not subject.isdigit() or len(subject)>255:raise ValueError()
        return subject
    except (ValueError,TypeError,KeyError,AttributeError):
        raise HTTPException(400,"Invalid Meta signed request") from None

@router.get("/data-deletion",response_class=HTMLResponse,include_in_schema=False)
def instructions():
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pruvs data deletion</title><main><h1>Pruvs data deletion</h1><p>To delete your Pruvs account and associated data, sign in, open Account and use the account deletion option. Confirm the request using your verified email. If you used Facebook, you can also disconnect Facebook under Connected social accounts. Disconnecting Facebook does not delete receipts or your Pruvs account.</p><p>If you cannot sign in, use Forgot password with your verified email or contact support through Pruvs. Some data may be retained where legally required.</p><p><a href="/login">Sign in</a> · <a href="/reset">Recover account</a> · <a href="/privacy">Privacy notice</a></p></main></html>"""

@router.post("/api/v1/auth/social/facebook/deauthorize",include_in_schema=False)
async def deauthorize(request:Request,db=Depends(get_db)):
    if int(request.headers.get("content-length") or 0)>8192:raise HTTPException(413,"Request too large")
    form=await request.form()
    subject=verify_signed_request(str(form.get("signed_request") or ""),os.getenv("FACEBOOK_CLIENT_SECRET",""))
    identity=db.query(SocialAccount).filter_by(provider="facebook",subject=subject).with_for_update().first()
    if identity:
        revoke_user(db,identity.user_id)
        db.delete(identity)
        db.commit()
    return {"ok":True}
