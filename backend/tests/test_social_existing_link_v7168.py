"""Existing-account linking: exercise real ORM rows, OTP consumption and session issuance."""
import importlib, pkgutil, time
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.models.user import User
from app.models.social_identity import SocialAccount
from app.models.verification_code import VerificationCode
from app.models.react_session import ReactSession
from app.react_app import social_auth as social
from app.services import onboarding_otp_service as otp

@pytest.fixture
def setup(tmp_path, monkeypatch):
    import app.models
    for m in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module("app.models."+m.name)
    engine=create_engine("sqlite:///"+str(tmp_path/"link.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setenv("PRUVS_SOCIAL_AUTH_STATE_SECRET","state-secret-"+"x"*40)
    monkeypatch.setenv("OTP_SECRET","otp-test-"+"x"*40)
    monkeypatch.setattr(social,"_ensure_provider",lambda p:None)
    monkeypatch.setattr(social,"limit",lambda *args:None)
    monkeypatch.setattr(otp,"generate_otp_code",lambda:"123456")
    monkeypatch.setattr(otp,"_deliver",lambda *args,**kwargs:{"sent":True})
    with Session(engine) as db:
        user=User(phone_number="+40722000321",username="existing.user",username_key="existing.user",
                  email="existing@example.org",status="active",is_email_verified=True)
        db.add(user);db.commit()
        yield db,user.id
    engine.dispose()

def req(provider, *, verified=True, nonce="flow-one", email="existing@example.org", subject="subject-one"):
    ticket={"iat":int(time.time()),"provider":provider,"subject":subject,"name":"Test",
            "verified":verified,"email":email if verified else "","link_nonce":nonce,"next":"/bills"}
    cookie=social.SIGNUP_COOKIE+"="+social._seal(ticket)
    return Request({"type":"http","method":"POST","path":"/existing","headers":[(b"cookie",cookie.encode())],"query_string":b""})

@pytest.mark.parametrize("provider,verified",[("google",True),("linkedin",True),("yahoo",True),("facebook",False),("tiktok",False)])
def test_link_existing_account_once(setup,provider,verified):
    db,uid=setup
    request=req(provider,verified=verified)
    start=social.existing_send(social.ExistingLinkStart(email="existing@example.org"),request,db)
    assert db.query(User).count()==1
    assert db.query(SocialAccount).count()==0
    assert db.query(ReactSession).count()==0
    payload=social.ExistingLinkVerify(email="existing@example.org",challenge_id=start["challenge_id"],code="123456")
    result=social.existing_verify(payload,request,Response(),db)
    assert result["user"]["id"]==uid
    assert db.query(User).count()==1
    assert db.query(SocialAccount).one().user_id==uid
    assert db.query(SocialAccount).one().provider==provider
    assert db.query(VerificationCode).one().status=="verified"
    assert db.query(ReactSession).count()==1
    with pytest.raises(HTTPException):
        social.existing_verify(payload,request,Response(),db)
    assert db.query(ReactSession).count()==1

def test_wrong_flow_wrong_code_and_email(setup):
    db,uid=setup
    request=req("yahoo")
    start=social.existing_send(social.ExistingLinkStart(),request,db)
    payload=social.ExistingLinkVerify(challenge_id=start["challenge_id"],code="123456")
    with pytest.raises(HTTPException):
        social.existing_verify(payload,req("yahoo",nonce="different"),Response(),db)
    with pytest.raises(HTTPException):
        social.existing_verify(payload,req("google"),Response(),db)
    with pytest.raises(HTTPException):
        social.existing_verify(payload.model_copy(update={"email":"other@example.org"}),request,Response(),db)
    with pytest.raises(HTTPException):
        social.existing_verify(payload.model_copy(update={"code":"654321"}),request,Response(),db)
    assert db.query(SocialAccount).count()==0
    assert db.query(ReactSession).count()==0
    assert db.query(VerificationCode).one().attempts==1

@pytest.mark.parametrize("change",["blocked","unverified","duplicate","email","provider-conflict"])
def test_account_changes_fail_closed(setup,change):
    db,uid=setup
    request=req("yahoo")
    start=social.existing_send(social.ExistingLinkStart(),request,db)
    user=db.get(User,uid)
    if change=="blocked":user.status="blocked"
    elif change=="unverified":user.is_email_verified=False
    elif change=="email":user.email="changed@example.org"
    elif change=="duplicate":db.add(User(phone_number="+40722000322",username="other.user",username_key="other.user",email="existing@example.org",status="active",is_email_verified=True))
    else:db.add(SocialAccount(user_id=uid,provider="yahoo",subject="other-subject"))
    db.commit()
    with pytest.raises(HTTPException):
        social.existing_verify(social.ExistingLinkVerify(challenge_id=start["challenge_id"],code="123456"),request,Response(),db)
    assert db.query(ReactSession).count()==0
    assert db.query(SocialAccount).count()==int(change=="provider-conflict")

def test_unknown_email_does_not_create_user(setup):
    db,uid=setup
    r=social.existing_send(social.ExistingLinkStart(email="missing@example.org"),req("tiktok",verified=False),db)
    assert r["challenge_id"]
    assert db.query(User).count()==1
    assert db.query(VerificationCode).count()==0

def test_existing_link_requires_own_otp_purpose(setup):
    db,uid=setup
    user=db.get(User,uid)
    row,_=otp.create_verification_code(db,user,"email",user.email,"registration")
    with pytest.raises(HTTPException):
        social.existing_verify(social.ExistingLinkVerify(challenge_id=row.challenge_id,code="123456"),req("yahoo"),Response(),db)
    assert db.query(SocialAccount).count()==0
