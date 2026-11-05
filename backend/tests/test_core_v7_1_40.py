"""Isolated Core v7.1.40 regression tests; NEVER connect to DATABASE_URL from staging/prod.

Pytest fixture creates an in-memory SQLite database with no actual credentials,
fixtures, notifications, uploads, or remote service calls.
"""
import sys
import types
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

# Existing translation backfill is unrelated to allocation; no LLM/API calls in tests.
mock_translation=types.ModuleType('app.services.receipt_translation_service')
mock_translation.translate_receipt_item_names=lambda _:None
sys.modules.setdefault('app.services.receipt_translation_service',mock_translation)

from app.db.database import Base
import app.models,importlib,pkgutil
for mod in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module('app.models.'+mod.name)
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.receipt_group import ReceiptGroup,ReceiptGroupMembership
from app.models.split_bill_v7140 import SplitAllocationState,SplitSharedItem
from app.react_app import split_v7140 as allocation
from app.react_app.bill_service import save_participant_selection
from app.react_app import receipt_groups_v7140 as groups

@pytest.fixture
def populated():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine)()
    try:
        owner=User(phone_number='+40110000000',name='Owner',status='active')
        other=User(phone_number='+40110000001',name='Another owner',status='active')
        db.add_all([owner,other]);db.flush()
        case=Case(user_id=owner.id,status='ready')
        foreign_case=Case(user_id=other.id,status='ready')
        db.add_all([case,foreign_case]);db.flush()
        doc=Document(case_id=case.id,stored_filename='test.jpg',path='local://test.jpg')
        db.add(doc);db.flush()
        # 2 pizza at 40 each, one fractional total 1.01, 4 people.
        pizza=ReceiptItem(case_id=case.id,document_id=doc.id,name='Pizza',quantity=2,
                           unit_price=40,total_price=80,currency='RON',source_language='en')
        juice=ReceiptItem(case_id=case.id,document_id=doc.id,name='Juice',quantity=1,
                          unit_price=1.01,total_price=1.01,currency='RON',source_language='en')
        db.add_all([pizza,juice]);db.flush()
        session=SplitBillSession(case_id=case.id,owner_user_id=owner.id,
                                 token='sb_test_v7140',expected_participants_count=4,currency='RON')
        db.add(session);db.flush()
        participants=[]
        for i in range(4):
            p=SplitBillParticipant(session_id=session.id,user_id=owner.id if i==0 else None,
                display_name=f'Guest {i}',participant_token=f'pt_{i}',role='owner' if i==0 else 'participant',status='joined')
            db.add(p);participants.append(p)
        db.commit()
        yield db,owner,other,case,foreign_case,session,pizza,juice,participants
    finally:
        db.close();engine.dispose()

def test_groups_are_owner_scoped(populated):
    db,owner,other,case,foreign_case,*_=populated
    g=groups.create_group({'name':'Trip to Rome'},identity=(owner,None),db=db)
    assert g['receipt_count']==0
    assert groups.assign_group(g['id'],case.id,(owner,None),db)['group_id']==g['id']
    assert groups.list_groups((owner,None),db)['groups'][0]['receipt_count']==1
    with pytest.raises(HTTPException) as err:
        groups.assign_group(g['id'],foreign_case.id,(owner,None),db)
    assert err.value.status_code==404
    with pytest.raises(HTTPException):
        groups.delete_group(g['id'],(other,None),db)
    assert groups.delete_group(g['id'],(owner,None),db)['receipts_deleted']==0
    assert db.get(Case,case.id) is not None
    assert db.get(ReceiptGroupMembership,case.id) is None

def test_equal_split_exact_and_restore(populated):
    db,owner,_,_,_,s,pizza,juice,participants=populated
    pid=participants[0].id
    manual=SplitBillItemAssignment(session_id=s.id,participant_id=pid,receipt_item_id=pizza.id,
                                   quantity=1,amount=40)
    db.add(manual);db.commit()
    allocation.set_equal_mode(db,s,owner.id,0)
    state=allocation.state_for(db,s.id)
    assert state.mode=='equal' and state.revision==1
    rows=db.query(SplitBillItemAssignment).filter_by(session_id=s.id).all()
    assert len(rows)==8
    assert round(sum(row.amount for row in rows),2)==81.01
    assert [round(sum(row.amount for row in rows if row.participant_id==p.id),2) for p in participants] == [20.26,20.25,20.25,20.25]
    assert all(row.quantity==0.5 for row in rows if row.receipt_item_id==pizza.id)
    with pytest.raises(HTTPException) as err:
        allocation.restore_item_mode(db,s,owner.id,0)
    assert err.value.status_code==409
    allocation.restore_item_mode(db,s,owner.id,1)
    restored=db.query(SplitBillItemAssignment).filter_by(session_id=s.id).all()
    assert len(restored)==1 and restored[0].participant_id==pid
    assert restored[0].amount==40.0 and restored[0].quantity==1.0
    assert allocation.state_for(db,s.id).revision==2

def test_shared_item_has_more_people_than_quantity(populated):
    db,owner,_,_,_,s,pizza,juice,people=populated
    ids=[p.id for p in people]
    # One JUICE unit can be shared by four people, without changing OCR source.
    allocation.share_item(db,s,owner.id,juice.id,ids,0)
    assert db.get(ReceiptItem,juice.id).quantity==1
    rows=db.query(SplitBillItemAssignment).filter_by(receipt_item_id=juice.id).all()
    assert len(rows)==4
    assert sorted(int(round(a.amount*100)) for a in rows)==[25,25,25,26]
    assert sum(int(round(a.amount*100)) for a in rows)==101
    assert all(a.quantity==0.25 for a in rows)
    # Editing a different item must preserve the shared-line allocations.
    save_participant_selection(db,s,people[0].id,selected_quantities={pizza.id:1,juice.id:0.25})
    rows=db.query(SplitBillItemAssignment).filter_by(receipt_item_id=juice.id).all()
    assert len(rows)==4 and sum(int(round(a.amount*100)) for a in rows)==101
    with pytest.raises(HTTPException):
        allocation.unshare_item(db,s,owner.id,juice.id,0)
    allocation.unshare_item(db,s,owner.id,juice.id,2)
    assert db.query(SplitBillItemAssignment).filter_by(receipt_item_id=juice.id).count()==0

def test_equal_cannot_override_shared_items(populated):
    db,owner,_,_,_,s,pizza,juice,people=populated
    allocation.share_item(db,s,owner.id,juice.id,[p.id for p in people],0)
    with pytest.raises(ValueError,match='Remove shared-item'):
        allocation.set_equal_mode(db,s,owner.id,1)

def test_owner_and_open_status_required(populated):
    db,owner,other,_,_,s,*_=populated
    with pytest.raises(HTTPException) as err:
        allocation.set_equal_mode(db,s,other.id,0)
    assert err.value.status_code==403
    s.status='settled';db.commit()
    with pytest.raises(ValueError,match='open bill'):
        allocation.set_equal_mode(db,s,owner.id,0)

@pytest.mark.parametrize('total,n,result',[(1,2,[1,0]),(3,4,[1,1,1,0]),(8000,4,[2000]*4),(101,4,[26,25,25,25])])
def test_cents_exact(total,n,result):
    assert list(allocation.allocate_evenly(total,list(range(1,n+1))).values())==result
