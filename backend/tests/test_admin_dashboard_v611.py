import importlib
import pkgutil
import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.models
from app.db.database import Base, get_db
from app.models.user import User
from app.models.admin_audit import AdminAudit
from app.api.users import router
from app.services import admin_dashboard_service as svc

for mod in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module('app.models.' + mod.name)

@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all([User(id=1,username='admin',username_key='admin',phone_number='+40700000001',status='active',is_admin=True),
                         User(id=2,username='member',username_key='member',phone_number='+40700000002',status='active')])
        session.commit()
        yield session
    engine.dispose()

@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setenv('PRUVS_ADMIN_API_KEY','test-only-admin-key')
    api = FastAPI();api.include_router(router,prefix='/users')
    api.dependency_overrides[get_db] = lambda: db
    with TestClient(api) as c:
        yield c

HEADERS={'X-Pruvs-Admin-Key':'test-only-admin-key'}

def test_role_api_requires_key(client, db):
    assert client.patch('/users/2',json={'is_admin':True}).status_code==401
    assert not db.get(User,2).is_admin
    response=client.patch('/users/2',json={'is_admin':True},headers=HEADERS)
    assert response.status_code==200, response.text
    assert response.json()['is_admin'] is True
    assert db.query(AdminAudit).count()==1
    assert client.patch('/users/2',json={'is_admin':False},headers=HEADERS).status_code==200
    assert not db.get(User,2).is_admin

def test_create_admin_and_regular_defaults(client, db):
    response=client.post('/users/',json={'username':'new.admin','phone_number':'+40700000003','email':'new@example.com','is_admin':True},headers=HEADERS)
    assert response.status_code==201, response.text
    assert response.json()['is_admin'] is True
    assert response.json()['status']=='pending_join'
    assert 'password_hash' not in response.json()
    response=client.post('/users/',json={'username':'new.member','phone_number':'+40700000004'},headers=HEADERS)
    assert response.status_code==201
    assert response.json()['is_admin'] is False

@pytest.mark.parametrize('actor_id',[None,2,999])
def test_regular_and_missing_users_denied(db,actor_id):
    for operation in [lambda:svc.catalog(db,actor_id),lambda:svc.list_records(db,actor_id,'users'),lambda:svc.get_record(db,actor_id,'users',1),lambda:svc.export_csv(db,actor_id,'users')]:
        with pytest.raises(PermissionError):operation()

def test_role_and_status_rechecked(db):
    svc.catalog(db,1)
    db.get(User,1).is_admin=False;db.commit()
    with pytest.raises(PermissionError):svc.list_records(db,1,'users')
    db.get(User,1).is_admin=True;db.get(User,1).status='blocked';db.commit()
    with pytest.raises(PermissionError):svc.catalog(db,1)

def test_ui_cannot_change_role_or_sensitive_fields(db):
    _,version=svc.get_record(db,1,'users',2)
    for fields in [{'is_admin':True},{'password_hash':'fake'},{'accepted_terms':True}]:
        with pytest.raises(ValueError):svc.update_record(db,1,'users',2,fields,version)
    assert not db.get(User,2).is_admin

def test_edits_audit_and_concurrent_conflict(db):
    _,version=svc.get_record(db,1,'users',2)
    svc.update_record(db,1,'users',2,{'name':'Updated'},version)
    assert db.get(User,2).name=='Updated'
    assert db.query(AdminAudit).one().changed_fields=='["name"]'
    with pytest.raises(ValueError,match='changed'):
        svc.update_record(db,1,'users',2,{'name':'Stale'},version)
    assert db.get(User,2).name=='Updated'

def test_all_tables_browse_without_secrets(db):
    assert len(svc.catalog(db,1))==18
    for entity in svc.models():
        svc.list_records(db,1,entity)
    user,_=svc.get_record(db,1,'users',1)
    assert 'password_hash' not in user
    assert not (set(c.name for c in svc.visible_columns(svc.model_for('verification_codes'))) & svc.HIDDEN)

def test_search_filter_export(db):
    total,rows=svc.list_records(db,1,'users',search='member')
    assert total==1 and rows[0]['id']==2
    total,_=svc.list_records(db,1,'users',filter_field='id',filter_value='1')
    assert total==1
    with pytest.raises(ValueError):svc.list_records(db,1,'users',sort='password_hash')
    db.get(User,2).name=' =HYPERLINK("bad")';db.commit()
    output=svc.export_csv(db,1,'users').decode('utf-8-sig')
    assert "' =HYPERLINK" in output
    assert 'password_hash' not in output

def test_amount_edit_locked_after_split(db):
    from app.models.case import Case
    from app.models.document import Document
    from app.models.receipt_item import ReceiptItem
    from app.models.split_bill_session import SplitBillSession
    db.add(Case(id=1,user_id=2));db.flush()
    db.add(Document(id=1,case_id=1,stored_filename='test',path='test'));db.flush()
    db.add(ReceiptItem(id=1,case_id=1,document_id=1,name='Coffee',quantity=1,total_price=10,currency='RON'));db.commit()
    _,version=svc.get_record(db,1,'receipt_items',1)
    svc.update_record(db,1,'receipt_items',1,{'total_price':12},version)
    db.add(SplitBillSession(case_id=1,owner_user_id=2,token='test'));db.commit()
    _,version=svc.get_record(db,1,'receipt_items',1)
    with pytest.raises(ValueError,match='locked'):
        svc.update_record(db,1,'receipt_items',1,{'total_price':15},version)
    svc.update_record(db,1,'receipt_items',1,{'name':'Espresso'},version)
    assert db.get(ReceiptItem,1).total_price==12

def test_split_settings_validate_state_and_limits(db):
    from app.models.case import Case
    from app.models.split_bill_session import SplitBillSession
    db.add(Case(id=1,user_id=2));db.flush()
    db.add(SplitBillSession(id=1,case_id=1,owner_user_id=2,token='test'));db.commit()
    _,version=svc.get_record(db,1,'split_bill_sessions',1)
    with pytest.raises(ValueError):
        svc.update_record(db,1,'split_bill_sessions',1,{'tip_mode':'percent','tip_value':101},version)
    svc.update_record(db,1,'split_bill_sessions',1,{'tip_mode':'percent','tip_value':10,'expected_participants_count':3},version)
    row=db.get(SplitBillSession,1)
    assert row.tip_value==10 and row.expected_participants_count==3
    row.status='settled';db.commit()
    _,version=svc.get_record(db,1,'split_bill_sessions',1)
    with pytest.raises(ValueError,match='owner'):
        svc.update_record(db,1,'split_bill_sessions',1,{'tip_value':15},version)

def test_existing_database_role_migration_is_idempotent(monkeypatch):
    from sqlalchemy import text, inspect
    from app.db import database
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(User.__table__.insert().values(id=99,phone_number="+40700000099",username="legacy",username_key="legacy"))
        connection.execute(text('ALTER TABLE users DROP COLUMN is_admin'))
    monkeypatch.setattr(database,'engine',engine)
    database.ensure_compatibility_schema()
    database.ensure_compatibility_schema()
    assert 'is_admin' in {c['name'] for c in inspect(engine).get_columns('users')}
    with engine.connect() as connection:
        assert connection.execute(text('SELECT is_admin FROM users WHERE id=99')).scalar()==0
    engine.dispose()
