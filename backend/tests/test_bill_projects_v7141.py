"""Isolated in-memory project tests; no staging/production connections or secrets."""
import importlib
import pkgutil
import sys
import types
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Disable network translation; not relevant to project accounting.
translation=types.ModuleType('app.services.receipt_translation_service')
translation.translate_receipt_item_names=lambda *args,**kwargs:None
sys.modules.setdefault('app.services.receipt_translation_service',translation)
from app.db.database import Base
import app.models
for entry in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module('app.models.'+entry.name)
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.payment_profile import PaymentProfile
from app.models.group_project_v7141 import BillProject, BillProjectMember, BillProjectItem
from app.react_app import bill_projects_v7141 as projects

@pytest.fixture
def data(monkeypatch):
    monkeypatch.setenv('PRUVS_CORE_V7141_PROJECTS_ENABLED','true')
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine)()
    owner=User(phone_number='+40110009991',name='Owner',status='active')
    participant=User(phone_number='+40110009992',name='Participant',status='active')
    outsider=User(phone_number='+40110009993',name='Outsider',status='active')
    db.add_all([owner,participant,outsider]);db.flush()
    receipts=[]
    for amount,curr in [(10.01,'RON'),(30.0,'EUR')]:
        case=Case(user_id=owner.id,module='receipt',status='ready')
        db.add(case);db.flush()
        doc=Document(case_id=case.id,stored_filename='test.jpg',path='local://test.jpg')
        db.add(doc);db.flush()
        item=ReceiptItem(case_id=case.id,document_id=doc.id,name='Food',quantity=1,unit_price=amount,total_price=amount,currency=curr,source_language='en')
        db.add(item);db.flush()
        s=SplitBillSession(case_id=case.id,owner_user_id=owner.id,token=f'test-project-{curr}',expected_participants_count=2,currency=curr)
        db.add(s);db.flush()
        p_owner=SplitBillParticipant(session_id=s.id,user_id=owner.id,display_name='Owner',participant_token=f'owner-{curr}',role='owner',status='joined')
        p_other=SplitBillParticipant(session_id=s.id,user_id=participant.id,display_name='Participant',participant_token=f'other-{curr}',role='participant',status='joined',payment_status='unpaid')
        db.add_all([p_owner,p_other]);db.flush()
        split_1=round(amount/2,2)
        split_2=round(amount-split_1,2)
        db.add_all([SplitBillItemAssignment(session_id=s.id,participant_id=p_owner.id,receipt_item_id=item.id,quantity=.5,amount=split_1),
                    SplitBillItemAssignment(session_id=s.id,participant_id=p_other.id,receipt_item_id=item.id,quantity=.5,amount=split_2)])
        receipts.append((case,s,p_other))
    foreign=Case(user_id=outsider.id,module='receipt',status='ready');db.add(foreign)
    profile=PaymentProfile(user_id=participant.id,label='My bank',recipient_name='Participant',iban='RO49AAAA1B31007593840000',bank_name='Test bank')
    db.add(profile);db.commit()
    try:yield db,owner,participant,outsider,receipts,foreign,profile
    finally:db.close();engine.dispose()

def create(data):
    db,owner,_,_,_,_,_=data
    response=projects.create_project({'name':'Ski Trip'},identity=(owner,None),db=db)
    return response['id']

def test_project_add_invites_but_requires_acceptance(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    case,s,_=receipts[0]
    added=projects.add_project_items(pid,{'items':[{'kind':'split','source_id':s.id}]},(owner,None),db)
    assert added=={'added':1,'new_invitations':1,'requires_invitation_acceptance':True}
    invited=projects.list_projects((other,None),db)['projects']
    assert invited[0]['membership_status']=='invited'
    with pytest.raises(HTTPException) as error:
        projects.project_detail(pid,(other,None),db)
    assert error.value.status_code==404
    projects.accept_project(pid,(other,None),db)
    assert projects.project_detail(pid,(other,None),db)['members'][1]['status']=='joined'
    with pytest.raises(HTTPException):projects.project_detail(pid,(outsider,None),db)

def test_foreign_source_not_importable(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    with pytest.raises(HTTPException) as exc:
        projects.add_project_items(pid,{'items':[{'kind':'receipt','source_id':foreign.id}]},(owner,None),db)
    assert exc.value.status_code==404
    assert projects.project_detail(pid,(owner,None),db)['items']==[]

def test_currency_totals_are_separate_and_receipt_not_counted_twice(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    case1,s1,other1=receipts[0]
    case2,s2,other2=receipts[1]
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':s1.id},
        {'kind':'split','source_id':s2.id},{'kind':'receipt','source_id':case1.id}]},(owner,None),db)
    summary=projects.project_detail(pid,(owner,None),db)
    assert summary['currencies']['RON']['bill_total']==10.01
    assert summary['currencies']['EUR']['bill_total']==30.0
    assert summary['currencies']['RON']['unassigned']==0.0
    assert len(summary['items'])==3
    people=[p for p in summary['participants'] if p['user_id']==other.id]
    assert len(people)==1
    assert people[0]['bill_count']==2
    assert people[0]['currencies']['EUR']['outstanding']==15.0
    assert people[0]['currencies']['RON']['outstanding']>0
    other1.payment_status='paid'
    db.commit()
    summary=projects.project_detail(pid,(owner,None),db)
    assert summary['currencies']['RON']['reported']>0
    assert summary['currencies']['RON']['confirmed']==0.0
    other1.payment_status='received';db.commit()
    summary=projects.project_detail(pid,(owner,None),db)
    assert summary['currencies']['RON']['confirmed']>0
    assert summary['participants'][1]['currencies']['RON']['outstanding']==0.0

def test_receipt_only_has_unallocated_not_participant_debt(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    case,*_=receipts[0]
    projects.add_project_items(pid,{'items':[{'kind':'receipt','source_id':case.id}]},(owner,None),db)
    summary=projects.project_detail(pid,(owner,None),db)
    assert summary['currencies']['RON']['bill_total']==10.01
    assert summary['currencies']['RON']['unassigned']==10.01
    assert summary['participants']==[]

def test_payment_profile_requires_explicit_member_opt_in(data):
    db,owner,other,outsider,receipts,foreign,profile=data
    pid=create(data)
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':receipts[0][1].id}]},(owner,None),db)
    assert all(m['payment_profile'] is None for m in projects.project_detail(pid,(owner,None),db)['members'])
    with pytest.raises(HTTPException):
        projects.share_payment_profile(pid,{'payment_profile_id':profile.id},(owner,None),db)
    with pytest.raises(HTTPException):
        projects.share_payment_profile(pid,{'payment_profile_id':profile.id},(other,None),db)
    projects.accept_project(pid,(other,None),db)
    projects.share_payment_profile(pid,{'payment_profile_id':profile.id},(other,None),db)
    visible=[m for m in projects.project_detail(pid,(owner,None),db)['members'] if m['user_id']==other.id][0]
    assert visible['payment_profile']['iban']==profile.iban
    projects.share_payment_profile(pid,{'payment_profile_id':None},(other,None),db)
    visible=[m for m in projects.project_detail(pid,(owner,None),db)['members'] if m['user_id']==other.id][0]
    assert visible['payment_profile'] is None

def test_delete_project_keeps_original_data(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    case,s,_=receipts[0]
    projects.add_project_items(pid,{'items':[{'kind':'receipt','source_id':case.id},{'kind':'split','source_id':s.id}]},(owner,None),db)
    assert projects.delete_project(pid,(owner,None),db)['original_receipts_and_splits_preserved']
    assert db.get(Case,case.id) and db.get(SplitBillSession,s.id)
    assert db.query(BillProjectItem).filter_by(project_id=pid).count()==0

def test_feature_disabled_by_default(data,monkeypatch):
    db,owner,*_=data
    monkeypatch.delenv('PRUVS_CORE_V7141_PROJECTS_ENABLED')
    with pytest.raises(HTTPException) as exc:
        projects.list_projects((owner,None),db)
    assert exc.value.status_code==404


def test_manual_invite_and_revoke_are_owner_only(data):
    from starlette.requests import Request
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    req=Request({'type':'http','method':'POST','path':'/test',
                 'headers':[],'client':('127.0.0.1',12345),'query_string':b'',
                 'server':('test',443),'scheme':'https'})
    # Explicitly use a registered username; no email contact lookup.
    username=outsider.username
    with pytest.raises(HTTPException) as bad:
        projects.invite_username(pid,{'username':username},req,(other,None),db)
    assert bad.value.status_code==404
    response=projects.invite_username(pid,{'username':username},req,(owner,None),db)
    assert response['invited'] and response['membership_status']=='invited'
    assert projects.list_projects((outsider,None),db)['projects'][0]['membership_status']=='invited'
    assert projects.remove_project_member(pid,outsider.id,(owner,None),db)['revoked']
    with pytest.raises(HTTPException):projects.project_detail(pid,(outsider,None),db)

def test_duplicate_split_for_same_receipt_is_rejected(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    case,original,_=receipts[0]
    second=SplitBillSession(case_id=case.id,owner_user_id=owner.id,token='new-split-same-receipt',
                            currency='RON',expected_participants_count=2)
    db.add(second);db.commit()
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':original.id}]},(owner,None),db)
    with pytest.raises(ValueError,match='Only one split'):
        projects.add_project_items(pid,{'items':[{'kind':'split','source_id':second.id}]},(owner,None),db)
    assert len(projects.project_detail(pid,(owner,None),db)['items'])==1

def test_later_joined_participants_can_be_invited(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    case,session,_=receipts[0]
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':session.id}]},(owner,None),db)
    newcomer=SplitBillParticipant(session_id=session.id,user_id=outsider.id,display_name='Outsider',
            participant_token='new-joining-guest',role='participant',status='joined')
    db.add(newcomer);db.commit()
    result=projects.sync_participants(pid,(owner,None),db)
    assert result['new_invitations']==1
    assert projects.list_projects((outsider,None),db)['projects'][0]['membership_status']=='invited'

def test_accepted_member_may_contribute_owned_bill_and_preserve_its_payee(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    # Join project through participation on an original receipt.
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':receipts[0][1].id}]},(owner,None),db)
    projects.accept_project(pid,(other,None),db)
    case=Case(user_id=other.id,module='receipt',status='ready');db.add(case);db.flush()
    doc=Document(case_id=case.id,stored_filename='second.jpg',path='local://second.jpg')
    db.add(doc);db.flush()
    item=ReceiptItem(case_id=case.id,document_id=doc.id,name='Cab',quantity=1,unit_price=5,
                     total_price=5,currency='RON',source_language='en')
    db.add(item);db.flush()
    s=SplitBillSession(case_id=case.id,owner_user_id=other.id,token='other-owned-bill',
                       expected_participants_count=2,currency='RON')
    db.add(s);db.flush()
    p1=SplitBillParticipant(session_id=s.id,user_id=other.id,display_name='Participant',
                            participant_token='paid-the-cab',role='owner',status='joined')
    p2=SplitBillParticipant(session_id=s.id,user_id=owner.id,display_name='Owner',
                            participant_token='owed-for-cab',role='participant',status='joined')
    db.add_all([p1,p2]);db.flush()
    db.add_all([
      SplitBillItemAssignment(session_id=s.id,participant_id=p1.id,receipt_item_id=item.id,quantity=.5,amount=2.5),
      SplitBillItemAssignment(session_id=s.id,participant_id=p2.id,receipt_item_id=item.id,quantity=.5,amount=2.5)
    ]);db.commit()
    assert projects.add_project_items(pid,{'items':[{'kind':'split','source_id':s.id}]},(other,None),db)['added']==1
    report=projects.project_detail(pid,(owner,None),db)
    assert report['currencies']['RON']['bill_total']==15.01
    me=next(p for p in report['participants'] if p['user_id']==owner.id)
    assert {'currency':'RON','user_id':other.id,'recipient_name':other.name,'outstanding':2.5} in me['pay_to']
    assert projects.remove_project_item(pid,'split',s.id,(other,None),db)['removed']
    assert db.get(SplitBillSession,s.id) is not None

def test_revoking_member_removes_their_contributed_links(data):
    db,owner,other,outsider,receipts,foreign,_=data
    pid=create(data)
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':receipts[0][1].id}]},(owner,None),db)
    projects.accept_project(pid,(other,None),db)
    own=Case(user_id=other.id,status='ready',module='receipt');db.add(own);db.commit()
    projects.add_project_items(pid,{'items':[{'kind':'receipt','source_id':own.id}]},(other,None),db)
    assert any(r.source_id==own.id for r in db.query(BillProjectItem).filter_by(project_id=pid).all())
    result=projects.remove_project_member(pid,other.id,(owner,None),db)
    assert result['revoked'] is True and result['contributed_links_removed']==1
    assert db.get(Case,own.id) is not None
    assert not db.query(BillProjectItem).filter_by(project_id=pid,source_id=own.id).first()
