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


def test_passkey_signup_context_binds_browser_and_profile():
    from types import SimpleNamespace
    from app.react_app.api import _signup_context
    user=SimpleNamespace(id=42,email="test@example.org",phone_number="+40722000000",name="Test User",username="test.user",password_hash=None,accepted_terms=True,accepted_privacy=True)
    proof=_signup_context(user,"browser-a")
    assert proof != _signup_context(user,"browser-b")
    user.phone_number="+40722000001"
    assert proof != _signup_context(user,"browser-a")

def test_passkey_signup_fails_closed_when_flag_off(monkeypatch):
    from app.react_app.api import _passkey_signup_enabled
    monkeypatch.delenv("PASSKEY_SIGNUP_ENABLED",raising=False)
    with pytest.raises(HTTPException) as err:
        _passkey_signup_enabled()
    assert err.value.status_code==503

def test_verified_email_collision_redirects_without_linking(tmp_path,monkeypatch):
    import importlib,pkgutil,app.models
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.database import Base
    from app.models.user import User
    from app.models.social_identity import SocialAccount
    from starlette.requests import Request
    for m in pkgutil.iter_modules(app.models.__path__):importlib.import_module("app.models."+m.name)
    engine=create_engine("sqlite:///"+str(tmp_path/"collision.db"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(phone_number="+40722000123",username="test.guest",username_key="test.guest",email="user@example.org",status="active",is_email_verified=True));db.commit()
        req=Request({"type":"http","method":"GET","path":"/callback","headers":[],"query_string":b""})
        response=social._finish_verified_identity("yahoo",{"subject":"new-yahoo","name":"Test","email":"USER@example.org","verified":True},{"mode":"login","next":"/rewards"},req,db)
        assert response.status_code==303
        assert "social_error=existing_account" in response.headers["location"]
        assert db.query(User).count()==1
        assert db.query(SocialAccount).count()==0
    engine.dispose()
