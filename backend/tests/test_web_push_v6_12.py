import base64
import importlib
import pkgutil
from datetime import datetime, timedelta
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.database import Base, get_db
import app.models
for module in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module('app.models.' + module.name)
from app.models.user import User
from app.models.push_notification import PushDevice, PushEvent, PushDelivery
from app.services import push_service as s, push_worker as w
from app.api.push_notifications import router


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(s, 'SessionLocal', factory)
    monkeypatch.setattr(w, 'SessionLocal', factory)
    for key in ('PRUVS_VAPID_PUBLIC_KEY','PRUVS_VAPID_PRIVATE_KEY','PRUVS_VAPID_SUBJECT'):
        monkeypatch.setenv(key, 'test-only')
    monkeypatch.setenv('PRUVS_PUSH_ENABLED','true')
    with factory() as db:
        for uid in (1,2):
            db.add(User(id=uid, phone_number=f'+40000000{uid}', status='active',
                        email=f'user{uid}@example.com', is_email_verified=True, notifications_opt_in=True))
        db.commit()
    yield factory
    engine.dispose()


def subscription(suffix='1'):
    def enc(x): return base64.urlsafe_b64encode(x).decode().rstrip('=')
    return {'endpoint':'https://fcm.googleapis.com/fcm/send/test'+suffix,
            'keys':{'auth':enc(b'a'*16),'p256dh':enc(b'\x04'+b'b'*64)}}


def device(factory, uid=1, suffix='1', confirmed=True):
    token=s.create_grant(uid)
    with factory() as db:
        row=s.register_device(db,s.grant_for(db,token),subscription(suffix),'Test device')
        if confirmed: row.confirmed_at=datetime.utcnow(); db.commit()
        return token,row.id


def event(factory, kind='reminder'):
    with factory() as db:
        e=s.enqueue(db,1,kind,'Reminder','Please review your bill.');db.commit();return e.id


def test_confirm_requires_same_account_and_current_grant(env):
    token,did=device(env,confirmed=False); other=s.create_grant(2)
    with env() as db:
        e=s.test_device(db,s.grant_for(db,token),did)
        with pytest.raises(ValueError): s.confirm_test(db,s.grant_for(db,other),e.confirmation)
        row=s.confirm_test(db,s.grant_for(db,token),e.confirmation)
        assert row.confirmed_at
        with pytest.raises(ValueError): s.confirm_test(db,s.grant_for(db,token),e.confirmation)


def test_expired_confirmation_and_test_rate_limit(env):
    token,did=device(env,confirmed=False)
    with env() as db:
        grant=s.grant_for(db,token);e=s.test_device(db,grant,did)
        with pytest.raises(ValueError):s.test_device(db,grant,did)
        db.get(PushDevice,did).test_expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
        with pytest.raises(ValueError):s.confirm_test(db,grant,e.confirmation)


def test_logout_revokes_registration_and_token(env,monkeypatch):
    token,did=device(env);s.revoke_grant(token)
    with env() as db:
        assert s.grant_for(db,token) is None
        assert not db.get(PushDevice,did).active
    push=Mock();monkeypatch.setattr(w,'send_push',push);monkeypatch.setattr(w,'send_email',lambda *a:True)
    eid=event(env);w.run_once();assert not push.called
    with env() as db:assert db.get(PushEvent,eid).status=='email_accepted'


def test_subscription_cannot_be_transferred_between_users(env):
    device(env);token=s.create_grant(2)
    with env() as db:
        with pytest.raises(ValueError):s.register_device(db,s.grant_for(db,token),subscription(),'Other')


@pytest.mark.parametrize('endpoint',['http://fcm.googleapis.com/a','https://127.0.0.1/a','https://fcm.googleapis.com.evil.test/a','https://fcm.googleapis.com:999/a','https://user@fcm.googleapis.com/a','https://example.com/a'])
def test_ssrf_blocked(endpoint):
    value=subscription();value['endpoint']=endpoint
    with pytest.raises(ValueError):s.validate_subscription(value)


def test_retry_then_accept_and_no_duplicate_send(env,monkeypatch):
    device(env);eid=event(env);push=Mock(side_effect=[503,201]);monkeypatch.setattr(w,'send_push',push)
    w.run_once()
    with env() as db:
        e=db.get(PushEvent,eid);assert e.status=='pending';e.available_at=datetime.utcnow();db.commit()
    w.run_once();w.run_once();assert push.call_count==2
    with env() as db:assert db.get(PushEvent,eid).status=='accepted'


def test_dead_subscription_email_fallback(env,monkeypatch):
    _,did=device(env);eid=event(env)
    monkeypatch.setattr(w,'send_push',lambda *a:410);email=Mock(return_value=True);monkeypatch.setattr(w,'send_email',email)
    w.run_once()
    with env() as db:
        assert not db.get(PushDevice,did).active
        assert db.get(PushEvent,eid).status=='email_accepted'
    assert email.call_count==1


def test_unconfirmed_device_never_receives_business_notification(env,monkeypatch):
    device(env,confirmed=False);eid=event(env)
    push=Mock();monkeypatch.setattr(w,'send_push',push);monkeypatch.setattr(w,'send_email',lambda *a:True)
    w.run_once();assert not push.called


def test_preferences_prevent_delivery(env,monkeypatch):
    device(env);eid=event(env)
    with env() as db:s.preferences(db,1).reminders=False;db.commit()
    push=Mock();mail=Mock();monkeypatch.setattr(w,'send_push',push);monkeypatch.setattr(w,'send_email',mail)
    w.run_once();assert not push.called and not mail.called
    with env() as db:assert db.get(PushEvent,eid).status=='muted'


def test_multi_device_partial_success_retries_only_failed(env,monkeypatch):
    device(env,suffix='1');device(env,suffix='2');eid=event(env)
    push=Mock(side_effect=[201,503,201]);monkeypatch.setattr(w,'send_push',push)
    w.run_once()
    with env() as db:db.get(PushEvent,eid).available_at=datetime.utcnow();db.commit()
    w.run_once();assert push.call_count==3
    with env() as db:assert db.query(PushDelivery).filter_by(status='accepted').count()==2


def test_queue_claim_recovery_and_future_schedule(env):
    eid=event(env)
    with env() as db:
        e=w.claim(db);assert e.id==eid;assert w.claim(db) is None
        e.lease_until=datetime.utcnow()-timedelta(seconds=1);db.commit();assert w.claim(db).id==eid
        e.status='pending';e.available_at=datetime.utcnow()+timedelta(hours=1);db.commit();assert w.claim(db) is None


def test_api_auth_and_cross_account_disable(env):
    token,did=device(env);other=s.create_grant(2)
    app=FastAPI();app.include_router(router)
    def database():
        with env() as db:yield db
    app.dependency_overrides[get_db]=database
    with TestClient(app) as client:
        assert client.get('/notifications-api/state').status_code==401
        assert client.post('/notifications-api/disable',headers={'Authorization':'Bearer '+other},json={'device_id':did}).status_code==404
        response=client.get('/notifications-api/state',headers={'Authorization':'Bearer '+token})
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert 'subscription' not in response.text
        s.revoke_grant(token)
        assert client.get('/notifications-api/state',headers={'Authorization':'Bearer '+token}).status_code==401


def test_receipt_results_create_durable_events(env,monkeypatch):
    from types import SimpleNamespace
    from app.services import standalone_app_service as receipts
    monkeypatch.setattr(receipts,'save_document_bytes',lambda **kw:SimpleNamespace(id=123))
    monkeypatch.setattr(receipts,'process_document_with_azure_receipt_direct',lambda **kw:{'is_valid':True})
    with env() as db:
        result=receipts.create_standalone_receipt_case(db,file_bytes=b'test',original_filename='test.jpg',mime_type='image/jpeg',user_id=1)
        assert db.query(PushEvent).filter_by(user_id=1,kind='receipt_ready').count()==1
        monkeypatch.setattr(receipts,'process_document_with_azure_receipt_direct',Mock(side_effect=ValueError('mock OCR failure')))
        with pytest.raises(ValueError):receipts.create_standalone_receipt_case(db,file_bytes=b'test',original_filename='test.jpg',mime_type='image/jpeg',user_id=1)
        assert db.query(PushEvent).filter_by(user_id=1,kind='receipt_failed').count()==1


def test_settle_reopen_reminder_integration(env,monkeypatch):
    from app.models.case import Case
    from app.models.split_bill_session import SplitBillSession
    from app.models.split_bill_participant import SplitBillParticipant
    from app.services import split_bill_session_service as bills
    monkeypatch.setattr(bills,'get_split_bill_session_summary',lambda *a,**k:{'can_close':True})
    with env() as db:
        case=Case(user_id=1,module='split_bill',status='open');db.add(case);db.flush()
        session=SplitBillSession(case_id=case.id,owner_user_id=1,token='testbill',status='open');db.add(session);db.flush()
        for uid in (1,2):db.add(SplitBillParticipant(session_id=session.id,user_id=uid,display_name='Test',participant_token=f'p{uid}',role='owner' if uid==1 else 'participant',status='joined'))
        db.commit()
        bills.close_split_bill_session(db,session,1)
        assert db.query(PushEvent).filter_by(kind='bill_settled').count()==2
        bills.reopen_split_bill_session(db,session,1)
        assert db.query(PushEvent).filter_by(kind='bill_reopened').count()==2
        participant=db.query(SplitBillParticipant).filter_by(user_id=2).one()
        bills.send_participant_reminder(db,session,1,participant.id,'Please pay')
        assert db.query(PushEvent).filter_by(kind='reminder',user_id=2).count()==1
        with pytest.raises(ValueError):bills.send_participant_reminder(db,session,1,participant.id,'Please pay')
