"""Identity hardening contract tests."""
import hashlib,hmac,base64,json,time,logging
import pytest
from fastapi import HTTPException
from app.services.safe_access_log import SafeAccessFilter
from app.react_app.meta_privacy import verify_signed_request
from app.react_app import social_auth as social

def test_access_log_removes_query():
    r=logging.LogRecord("uvicorn.access",20,"",1,"%s %s %s %s %s",("ip","GET","/api/v1/auth/social/linkedin/callback?code=secret&state=private","1.1",303),None)
    assert SafeAccessFilter().filter(r)
    assert "secret" not in r.getMessage() and "private" not in r.getMessage()
    assert "callback?[redacted]" in r.getMessage()

def test_meta_signature():
    enc=lambda b:base64.urlsafe_b64encode(b).decode().rstrip("=")
    payload=enc(json.dumps({"algorithm":"HMAC-SHA256","user_id":"123","issued_at":int(time.time())}).encode())
    raw=enc(hmac.new(b"secret",payload.encode(),hashlib.sha256).digest())+"."+payload
    assert verify_signed_request(raw,"secret")=="123"
    with pytest.raises(HTTPException):verify_signed_request(raw,"wrong")

def test_linkedin_nonce_compatibility(monkeypatch):
    class JWKS:
        def __init__(self,*a):pass
        def get_signing_key_from_jwt(self,*a):
            return type("Key",(),{"key":"fake"})()
    monkeypatch.setattr(social.jwt,"PyJWKClient",JWKS)
    claims={"sub":"subject","email":"test@example.com","email_verified":True}
    monkeypatch.setattr(social.jwt,"decode",lambda *a,**k:claims)
    assert social._oidc_identity("linkedin",{"id_token":"test"},"client","nonce")["subject"]=="subject"
    with pytest.raises(HTTPException):social._oidc_identity("google",{"id_token":"test"},"client","nonce")
    claims["nonce"]="wrong"
    with pytest.raises(HTTPException):social._oidc_identity("linkedin",{"id_token":"test"},"client","nonce")
