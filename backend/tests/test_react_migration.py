"""Run against a disposable SQLite database; never touches the deployment database."""
import os
import tempfile
from pathlib import Path
_tmp=tempfile.TemporaryDirectory(prefix='pruvs-react-tests-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_tmp.name)/'test.db')
os.environ['PUBLIC_BASE_URL']='http://127.0.0.1:8098'
os.environ['PRUVS_PUSH_WORKER_ENABLED']='false'
os.environ['CANONICAL_REDIRECT_ENABLED']='false'
import pytest
from fastapi.testclient import TestClient
from app.react_main import app
from app.db.database import Base,engine,SessionLocal
if engine.url.get_backend_name()!='sqlite' or Path(engine.url.database).resolve().parent!=Path(_tmp.name).resolve():
    raise RuntimeError("Refusing to run destructive test fixtures outside their own temporary database. Run this test file in a fresh Python process.")
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.react_session import ReactSession
from app.models.push_notification import PushGrant,PushDevice
from app.services.password_service import hash_password
PASSWORD='LocalTestOnly123!'
HASH=hash_password(PASSWORD)
BASE='http://127.0.0.1:8098'

@pytest.fixture(autouse=True)
def database(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for uid,name in [(1,'owner'),(2,'guest'),(3,'admin')]:
            db.add(User(id=uid,phone_number='+4070000000'+str(uid),name=name.title(),username=name,username_key=name,email=name+'@example.com',status='active',is_email_verified=True,password_hash=HASH,is_admin=uid==3,preferred_language='en'))
        db.flush();db.add(Case(id=1,user_id=1,module='receipt',status='processed'));db.flush()
        db.add(Document(id=1,case_id=1,stored_filename='test.jpg',path='/not-a-real-receipt.jpg',mime_type='image/jpeg'));db.flush()
        db.add_all([ReceiptItem(id=1,case_id=1,document_id=1,name='Coffee',translated_name='Coffee',source_language='en',quantity=2,unit_price=10,total_price=20,currency='RON'),ReceiptItem(id=2,case_id=1,document_id=1,name='Meal',translated_name='Meal',source_language='en',quantity=1,unit_price=40,total_price=40,currency='RON')]);db.commit()
    from app.services import onboarding_otp_service as otp
    monkeypatch.setattr(otp,'generate_otp_code',lambda:'123456')
    monkeypatch.setattr(otp,'_deliver',lambda *a,**kw:{'sent':True,'provider':'test'})
    yield

def client(name=None):
    c=TestClient(app,base_url=BASE);c.headers.update({'X-Pruvs-Client':'react','Origin':BASE})
    if name:
        r=c.post('/api/v1/auth/login',json={'identifier':name,'password':PASSWORD});assert r.status_code==200,r.text
        d=r.json();c.headers.update({'X-CSRF-Token':d['csrf'],'X-Pruvs-User':str(d['user']['id'])})
    return c

def split(c):
    r=c.post('/api/v1/receipts/1/split',json={'people':2});assert r.status_code==200,r.text
    return '/api/v1/bills/'+r.json()['token']

def test_auth_cookie_and_data_boundary():
    c=client();assert c.get('/api/v1/me').status_code==401
    c=client('owner');assert c.get('/api/v1/me').json()['user']['id']==1
    assert 'password_hash' not in c.get('/api/v1/me').text
    assert c.get('/api/v1/history').json()['receipt_count']==1
    assert client('guest').get('/api/v1/receipts/1').status_code==404

def test_csrf_origin_and_stale_account():
    c=client('owner');data={'name':'Changed'}
    assert c.patch('/api/v1/account',json=data,headers={'X-CSRF-Token':''}).status_code==403
    assert c.patch('/api/v1/account',json=data,headers={'Origin':'https://evil.invalid'}).status_code==403
    assert c.patch('/api/v1/account',json=data,headers={'X-Pruvs-User':'2'}).status_code==409
    assert c.patch('/api/v1/account',json=data).status_code==200

def test_block_revokes_session_immediately():
    c=client('owner');a=client('admin')
    assert a.post('/api/v1/admin/users/1/block',json={'confirm':'1'}).status_code==200
    assert c.get('/api/v1/me').status_code==401
    assert client().post('/api/v1/auth/login',json={'identifier':'owner','password':PASSWORD}).status_code==400
    assert a.post('/api/v1/admin/users/1/unblock',json={'confirm':'1'}).status_code==200
    assert client('owner').get('/api/v1/me').status_code==200

def test_logout_detaches_device():
    c=client('owner')
    with SessionLocal() as db:
        grant=db.query(PushGrant).filter_by(user_id=1,active=True).first()
        db.add(PushDevice(id='device',user_id=1,grant_hash=grant.token_hash,endpoint_hash='endpoint',subscription='{}',label='Test',active=True));db.commit()
    assert c.post('/api/v1/auth/logout',json={}).status_code==200
    assert c.get('/api/v1/me').status_code==401
    with SessionLocal() as db:assert not db.get(PushDevice,'device').active

def test_full_bill_join_select_settle_payment_reopen():
    owner=client('owner');guest=client('guest');url=split(owner)
    assert guest.get(url).status_code==403
    assert guest.get(url+'/invite').json()['joined'] is False
    assert guest.post(url+'/join',json={}).status_code==200
    assert guest.post(url+'/action/settle',json={}).status_code==403
    assert owner.post(url+'/action/settle',json={}).status_code==400
    assert owner.put(url+'/selection',json={'quantities':{'1':1,'2':1}}).status_code==200
    assert guest.put(url+'/selection',json={'quantities':{'1':2}}).status_code==400
    assert guest.put(url+'/selection',json={'quantities':{'1':1}}).status_code==200
    r=owner.post(url+'/action/tip',json={'mode':'percent','value':10});assert r.status_code==200,r.text
    r=owner.post(url+'/action/settle',json={});assert r.status_code==200,r.text
    assert r.json()['status']=='settled'
    assert guest.put(url+'/selection',json={'quantities':{}}).status_code==400
    r=guest.post(url+'/action/payment',json={'method':'bank_transfer','paid':True});assert r.status_code==200,r.text
    r=owner.post(url+'/action/reopen',json={});assert r.status_code==200,r.text
    assert r.json()['status']=='open'

def test_nonfinite_bill_values_rejected():
    c=client('owner');url=split(c)
    assert c.put(url+'/selection',json={'quantities':{'1':'NaN'}}).status_code==400
    assert c.post(url+'/action/tip',json={'mode':'fixed','value':'Infinity'}).status_code==400

def test_admin_tables_hide_secrets_and_inspect_bills():
    a=client('admin');owner=client('owner');split(owner)
    assert owner.get('/api/v1/admin/catalog').status_code==403
    catalog=a.get('/api/v1/admin/catalog').json();assert len(catalog)>15
    for table in catalog:
        r=a.get('/api/v1/admin/records/'+table['key']);assert r.status_code==200,(table,r.text)
        for row in r.json()['rows']:assert not set(row)&{'password_hash','token_hash','subscription','csrf_hash','binding_hash','challenge','test_hash'}
    r=a.get('/api/v1/admin/users/1/bills/1');assert r.status_code==200,r.text
    assert r.json()['receipt']['items'][0]['name']=='Coffee'
    assert a.get('/api/v1/admin/users/2/bills/1').status_code==400
    assert a.get('/api/v1/admin/records/users/export').status_code==200

def test_admin_optimistic_concurrency_and_no_role_edit():
    a=client('admin');record=a.get('/api/v1/admin/records/users/1').json()
    assert a.patch('/api/v1/admin/records/users/1',json={'revision':record['revision'],'changes':{'is_admin':True}}).status_code==400
    assert a.patch('/api/v1/admin/records/users/1',json={'revision':record['revision'],'changes':{'name':'Updated'}}).status_code==200
    assert a.patch('/api/v1/admin/records/users/1',json={'revision':record['revision'],'changes':{'name':'Stale'}}).status_code==400

def test_admin_delete_retains_shared_history():
    a=client('admin');owner=client('owner');url=split(owner)
    r=a.post('/api/v1/admin/users/1/delete',json={'confirm':'1'});assert r.status_code==200,r.text
    with SessionLocal() as db:assert db.get(User,1).status=='deleted';assert db.get(Case,1) is not None
    assert owner.get(url).status_code==401
    assert a.post('/api/v1/admin/users/3/delete',json={'confirm':'3'}).status_code==400

def test_admin_user_edit_and_remove_from_active_listing():
    a=client('admin')
    record=a.get('/api/v1/admin/records/users/1').json()
    assert a.patch('/api/v1/admin/records/users/1',json={
        'revision':record['revision'],'changes':{'name':'New owner name','email':'new-owner@example.com'}
    }).status_code==200
    assert a.get('/api/v1/admin/records/users/1').json()['record']['name']=='New owner name'
    assert a.post('/api/v1/admin/users/1/delete',json={'confirm':'1'}).status_code==200
    active=a.get('/api/v1/admin/records/users').json()['rows']
    assert 1 not in [row['id'] for row in active]
    all_rows=a.get('/api/v1/admin/records/users?include_deleted=true').json()['rows']
    assert next(row for row in all_rows if row['id']==1)['status']=='deleted'

def test_admin_document_requires_matching_user_and_case():
    a=client('admin')
    url='/api/v1/admin/users/1/bills/1/documents/1/file'
    assert a.get(url).status_code==404  # Database file is absent on disk.
    assert a.get('/api/v1/admin/users/2/bills/1/documents/1/file').status_code==404
    assert client('guest').get(url).status_code==403

def test_admin_control_api_preserved(monkeypatch):
    monkeypatch.setenv('PRUVS_ADMIN_CONTROL_KEY','local-test-key')
    c=client();url='/admin/user-controls'
    assert c.get(url+'/users').status_code==403
    c.headers['X-Pruvs-Admin-Key']='local-test-key'
    assert c.get(url+'/users').status_code==200
    assert c.post(url+'/users/1/block',json={'reason':'test'}).status_code==200
    assert c.post(url+'/users/3/block',json={}).status_code==400
    assert c.get(url+'/audit').json()[0]['before_status']=='active'

def test_notifications_use_logged_in_identity():
    c=client('owner');r=c.get('/notifications-api/state');assert r.status_code==200,r.text
    assert c.put('/notifications-api/preferences',json={'push_enabled':False,'email_enabled':True,'receipts':True,'bills':True,'reminders':True}).status_code==200
    assert c.get('/notifications-api/state').json()['preferences']['push_enabled'] is False
    assert client('guest').get('/notifications-api/state').json()['preferences']['push_enabled'] is True

def test_password_change_invalidates_other_sessions():
    first=client('owner');second=client('owner')
    r=first.post('/api/v1/account/password',json={'current_password':PASSWORD,'new_password':'NewLocalTest456!'});assert r.status_code==200,r.text
    assert first.get('/api/v1/me').status_code==200
    assert second.get('/api/v1/me').status_code==401

def test_registration_otp_and_verification():
    c=client();r=c.post('/api/v1/auth/register',json={'name':'New User','username':'newuser','phone_number':'+40710000001','email':'newuser@example.com','password':PASSWORD,'accepted_terms':True,'accepted_privacy':True});assert r.status_code==200,r.text
    assert 'debug' not in r.text
    r=c.post('/api/v1/auth/register/verify',json={'email':'newuser@example.com','code':'123456','challenge_id':r.json()['challenge_id']});assert r.status_code==200,r.text
    assert c.get('/api/v1/me').json()['user']['is_email_verified']

def test_password_reset_otp():
    c=client();r=c.post('/api/v1/auth/reset',json={'email':'owner@example.com'});assert r.status_code==200,r.text
    r=c.post('/api/v1/auth/reset/confirm',json={'email':'owner@example.com','code':'123456','challenge_id':r.json()['challenge_id'],'password':'NewLocalTest456!'});assert r.status_code==200,r.text

def test_spa_and_legacy_links():
    with TestClient(app,base_url=BASE) as c:
        for url in ['/','/login','/account','/bill/example','/admin','/notifications']:
            r=c.get(url);assert r.status_code==200;assert '<div id="root">' in r.text
        assert c.get('/health').json()['frontend']=='React'
        assert c.get('/service-worker.js').headers['service-worker-allowed']=='/'
        assert c.get('/s/example',follow_redirects=False).headers['location']=='/join/example'
        assert c.get('/cases/1').status_code==404
        assert c.get('/api/v1/unknown').status_code==404

def test_websocket_membership_and_session_revocation():
    c=client('owner');url=split(c);token=url.split('/')[-1]
    with c.websocket_connect(BASE.replace('http','ws')+'/api/v1/live/'+token,headers={'origin':BASE}) as ws:
        assert ws.receive_json()['owner_user_id']==1
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client('guest').websocket_connect(BASE.replace('http','ws')+'/api/v1/live/'+token,headers={'origin':BASE}) as ws:ws.receive_json()

def settled_bill():
    owner=client('owner');guest=client('guest');url=split(owner)
    assert guest.post(url+'/join',json={}).status_code==200
    assert owner.put(url+'/selection',json={'quantities':{'1':1,'2':1}}).status_code==200
    assert guest.put(url+'/selection',json={'quantities':{'1':1}}).status_code==200
    assert owner.post(url+'/action/settle',json={}).status_code==200
    return owner,guest,url

def test_incoming_inbox_settle_and_reopen_once_excludes_actor():
    owner,guest,url=settled_bill()
    assert owner.get('/api/v1/inbox').json()['total']==0
    data=guest.get('/api/v1/inbox').json();assert data['total']==1
    assert data['rows'][0]['kind']=='split_settled'
    assert owner.post(url+'/action/reopen',json={}).status_code==200
    data=guest.get('/api/v1/inbox').json();assert data['total']==2
    assert data['rows'][0]['kind']=='split_reopened'
    assert owner.get('/api/v1/inbox').json()['total']==0

def test_inbox_read_unread_and_recipient_deeplink():
    owner,guest,url=settled_bill();eid=guest.get('/api/v1/inbox').json()['rows'][0]['id']
    assert owner.post('/api/v1/inbox/'+eid+'/read',json={}).status_code==404
    assert owner.get('/api/v1/notifications/'+eid+'/target').status_code==404
    assert guest.get('/api/v1/notifications/'+eid+'/target').json()['url']=='/bill/'+url.split('/')[-1]
    assert guest.get('/api/v1/inbox?unread=true').json()['total']==0
    assert guest.post('/api/v1/inbox/'+eid+'/read',json={'read':False}).status_code==200
    assert guest.get('/api/v1/inbox?unread=true').json()['total']==1
    assert guest.post('/api/v1/inbox/read-all',json={}).status_code==200
    assert guest.get('/api/v1/inbox?unread=true').json()['total']==0

def test_inbox_preserves_legacy_reads_and_excludes_test_receipts_self():
    from app.services.push_service import enqueue
    from app.react_app.inbox import PruvsInboxRead
    from datetime import datetime
    owner,guest,url=settled_bill();token=url.split('/')[-1]
    with SessionLocal() as db:
        event=enqueue(db,2,'split_reopened','Older message','Persisted message',f'/split-bill/sessions/{token}/join')
        db.add(PruvsInboxRead(user_id=2,event_id=event.id,read_at=datetime.utcnow()))
        enqueue(db,2,'test','Test','Do not include');enqueue(db,2,'receipt_ready','Receipt','Do not include')
        enqueue(db,1,'bill_settled','Old self notice','Do not include',f'/split-bill/sessions/{token}/join');db.commit()
    data=guest.get('/api/v1/inbox').json();assert data['total']==2
    assert next(e for e in data['rows'] if e['title']=='Older message')['read'] is True
    assert owner.get('/api/v1/inbox').json()['total']==0

def test_inbox_missing_membership_stays_in_inbox():
    from app.models.split_bill_participant import SplitBillParticipant
    owner,guest,url=settled_bill();eid=guest.get('/api/v1/inbox').json()['rows'][0]['id']
    with SessionLocal() as db:
        db.query(SplitBillParticipant).filter_by(user_id=2).update({'status':'left'});db.commit()
    r=guest.get('/api/v1/notifications/'+eid+'/target');assert r.status_code==200
    assert r.json()['url']=='/inbox'
    assert guest.get('/api/v1/inbox').json()['rows'][0]['can_open'] is False

def test_explicit_device_enable_opts_in_and_confirmation(monkeypatch):
    import base64
    from app.models.push_notification import PushEvent
    monkeypatch.setenv('PRUVS_PUSH_ENABLED','true')
    for k in ['PRUVS_VAPID_PUBLIC_KEY','PRUVS_VAPID_PRIVATE_KEY','PRUVS_VAPID_SUBJECT']:monkeypatch.setenv(k,'local-test-only')
    c=client('owner')
    with SessionLocal() as db:db.get(User,1).notifications_opt_in=False;db.commit()
    subscription={'endpoint':'https://fcm.googleapis.com/fcm/send/test-only','keys':{'auth':base64.urlsafe_b64encode(b'a'*16).decode(),'p256dh':base64.urlsafe_b64encode(b'\x04'+b'x'*64).decode()}}
    r=c.post('/api/v1/device/subscribe',json={'subscription':subscription,'label':'Test browser'});assert r.status_code==200,r.text
    assert c.get('/api/v1/me').json()['user']['notifications_opt_in'] is True
    device=r.json()['device_id'];r=c.post('/notifications-api/test',json={'device_id':device});assert r.status_code==200,r.text
    with SessionLocal() as db:code=db.get(PushEvent,r.json()['event_id']).confirmation
    assert client('guest').post('/notifications-api/confirm',json={'code':code}).status_code==400
    assert c.post('/notifications-api/confirm',json={'code':code}).status_code==200
    assert c.get('/notifications-api/state').json()['devices'][0]['confirmed_at']

def test_notification_worker_preserves_specific_preview_and_private_mode(monkeypatch):
    from app.react_app import push_worker as worker
    from app.services.push_service import enqueue
    from datetime import datetime
    c=client('owner');payloads=[]
    monkeypatch.setattr(worker,'enabled',lambda:True)
    monkeypatch.setattr(worker,'send_push',lambda d,p:payloads.append(p) or 201)
    with SessionLocal() as db:
        g=db.query(PushGrant).filter_by(user_id=1,active=True).first()
        db.add(PushDevice(id='device',user_id=1,grant_hash=g.token_hash,endpoint_hash='worker-test',subscription='{}',label='Test',active=True,confirmed_at=datetime.utcnow()));db.commit()
        e=enqueue(db,1,'reminder','Payment reminder','Please pay your share.');db.commit();worker.deliver(db,e)
        assert e.status=='accepted';assert payloads[-1]['body']=='Please pay your share.'
        monkeypatch.setenv('PRUVS_PUSH_PREVIEW_MODE','private')
        e=enqueue(db,1,'reminder','Payment reminder','Private message');db.commit();worker.deliver(db,e)
        assert 'Private message' not in str(payloads[-1])

def test_signup_optional_notifications_defaults_off():
    c=client();r=c.post('/api/v1/auth/register',json={'name':'Opt Out','username':'optout','phone_number':'+40710000003','email':'optout@example.com','password':PASSWORD,'accepted_terms':True,'accepted_privacy':True});assert r.status_code==200,r.text
    with SessionLocal() as db:assert db.query(User).filter_by(username='optout').first().notifications_opt_in is False

def test_contact_change_and_account_delete_otp():
    c=client('guest');r=c.post('/api/v1/account/contact',json={'channel':'email','value':'changed@example.com'});assert r.status_code==200,r.text
    r=c.post('/api/v1/account/contact/confirm',json={'channel':'email','value':'changed@example.com','code':'123456','challenge_id':r.json()['challenge_id']});assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf']
    assert c.get('/api/v1/me').json()['user']['email']=='changed@example.com'
    r=c.post('/api/v1/account/delete/request',json={});assert r.status_code==200,r.text
    r=c.post('/api/v1/account/delete/confirm',json={'code':'123456','challenge_id':r.json()['challenge_id']});assert r.status_code==200,r.text
    assert c.get('/api/v1/me').status_code==401
    with SessionLocal() as db:assert db.get(User,2) is None
