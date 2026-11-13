"""Project v7.1.43 regression suite: isolated SQLite only (never staging/production DB)."""
from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from test_bill_projects_v7141 import data, create
from app.models.project_activity_v7143 import ProjectManualBill, ProjectExpenseShare, ProjectChatMessage
from app.models.group_project_v7141 import BillProjectMember
from app.react_app import bill_projects_v7141 as p
from app.services.project_allocations_v7143 import allocate_minor, to_minor


def req():
    return Request({'type':'http','method':'POST','path':'/api/v1/bill-projects',
      'headers':[],'client':('127.0.0.1',12345),'query_string':b'',
      'server':('test',443),'scheme':'https'})


def join(db,pid,uid):
    db.add(BillProjectMember(project_id=pid,user_id=uid,status='joined',joined_at=datetime.utcnow()))
    db.commit()


def test_exact_cent_equal_percent_amount_and_share():
    people=[{'user_id':i} for i in (2,3,4)]
    assert allocate_minor(1001,'equal',people)=={2:334,3:334,4:333}
    assert allocate_minor(31500,'share',[{'user_id':1,'value':1},{'user_id':2,'value':2}])=={1:10500,2:21000}
    assert allocate_minor(1001,'percent',[{'user_id':1,'value':50},{'user_id':2,'value':50}])=={1:501,2:500}
    assert allocate_minor(1001,'amount',[{'user_id':1,'value':'5.01'},{'user_id':2,'value':'5.00'}])=={1:501,2:500}
    for bad in ('1.001','NaN','inf','-1',None):
        with pytest.raises(ValueError):to_minor(bad)
    with pytest.raises(ValueError):allocate_minor(1001,'percent',[{'user_id':1,'value':25}])
    with pytest.raises(ValueError):allocate_minor(1001,'amount',[{'user_id':1,'value':'5.00'}])


def test_project_creation_saves_smart_settle_default_currency(data):
    db,owner,*_=data
    pid=p.create_project({'name':'Trip','smart_settle':False,'primary_currency':'EUR'},(owner,None),db)['id']
    view=p.project_detail(pid,(owner,None),db)
    assert view['smart_settle'] is False and view['primary_currency']=='EUR'
    assert p.update_project_options(pid,{'smart_settle':True},(owner,None),db)=={'smart_settle':True}


def test_manual_bill_member_contribution_and_balances(data):
    db,owner,member,outsider,*_=data
    pid=create(data)
    join(db,pid,member.id)
    result=p.add_manual_bill(pid,{'merchant':'Parking','amount':'10.01','currency':'RON','mode':'equal',
              'participants':[{'user_id':owner.id},{'user_id':member.id}]},(member,None),db)
    assert result['amount']==10.01
    view=p.project_detail(pid,(owner,None),db)
    row=next(x for x in view['items'] if x['kind']=='manual')
    assert row['merchant']=='Parking' and row['total']==10.01
    assert view['outstanding_by_currency']['RON']==5.01
    assert view['project_settled'] is False
    assert len(view['suggested_settlements'])==1
    assert view['suggested_settlements'][0]['from_user_id']==owner.id
    assert view['suggested_settlements'][0]['to_user_id']==member.id
    with pytest.raises(HTTPException):
        p.add_manual_bill(pid,{'merchant':'Foreign','amount':'10','currency':'EUR',
               'paid_by_user_id':member.id,'participants':[{'user_id':owner.id}]},(owner,None),db)
    with pytest.raises(HTTPException):
        p.add_manual_bill(pid,{'merchant':'Invalid','amount':'10','currency':'EUR',
               'participants':[{'user_id':outsider.id}]},(owner,None),db)


def test_project_manual_payment_report_and_recipient_confirmation(data):
    db,owner,member,_,*_=data
    pid=create(data);join(db,pid,member.id)
    bill=p.add_manual_bill(pid,{'merchant':'Groceries','amount':'7.01','currency':'EUR','mode':'equal',
                'participants':[{'user_id':owner.id},{'user_id':member.id}]},(owner,None),db)
    bid=bill['id']
    with pytest.raises(HTTPException):
        p.settle_project_share(pid,'manual',bid,member.id,'report',(owner,None),db)
    with pytest.raises(HTTPException):
        p.settle_project_share(pid,'manual',bid,member.id,'confirm',(owner,None),db)
    assert p.settle_project_share(pid,'manual',bid,member.id,'report',(member,None),db)['status']=='reported'
    assert p.project_detail(pid,(owner,None),db)['project_settled'] is False
    assert p.settle_project_share(pid,'manual',bid,member.id,'confirm',(owner,None),db)['status']=='confirmed'
    view=p.project_detail(pid,(owner,None),db)
    assert view['project_settled'] is True
    assert view['outstanding_by_currency'].get('EUR',0)==0
    with pytest.raises(HTTPException):
        p.settle_project_share(pid,'manual',bid,member.id,'report',(member,None),db)


def test_receipt_allocation_and_nonowner_restriction(data):
    db,owner,member,outsider,receipts,*_=data
    pid=create(data);join(db,pid,member.id)
    case,_,_=receipts[0]
    p.add_project_items(pid,{'items':[{'kind':'receipt','source_id':case.id}]},(owner,None),db)
    values={'mode':'share','participants':[{'user_id':owner.id,'value':1},{'user_id':member.id,'value':2}]}
    with pytest.raises(HTTPException):
        p.allocate_imported_receipt(pid,case.id,values,(member,None),db)
    result=p.allocate_imported_receipt(pid,case.id,values,(owner,None),db)
    assert result['allocated'] and result['currency']=='RON'
    summary=p.project_detail(pid,(owner,None),db)
    assert summary['currencies']['RON']['unassigned']==0.0
    assert round(summary['outstanding_by_currency']['RON'],2)==6.67
    # Creating a conflicting linked split after allocation must not double count.
    split=receipts[0][1]
    p.add_project_items(pid,{'items':[{'kind':'split','source_id':split.id}]},(owner,None),db)
    with pytest.raises(HTTPException):
        p.allocate_imported_receipt(pid,case.id,values,(owner,None),db)


def test_chat_only_joined_members_and_rate_guard(data,monkeypatch):
    db,owner,member,outsider,*_=data
    pid=create(data)
    with pytest.raises(HTTPException):p.project_chat(pid,(outsider,None),db)
    monkeypatch.setattr(p,'limit',lambda *a,**kw:None)
    p.send_project_chat(pid,{'text':'Hi from owner'},req(),(owner,None),db)
    assert p.project_chat(pid,(owner,None),db)['messages'][0]['text']=='Hi from owner'
    with pytest.raises(HTTPException):p.send_project_chat(pid,{'text':'No access'},req(),(outsider,None),db)
    with pytest.raises(HTTPException):p.send_project_chat(pid,{'text':'Too soon'},req(),(owner,None),db)
    row=db.query(ProjectChatMessage).first();row.created_at=datetime.utcnow()-timedelta(seconds=3);db.commit()
    p.send_project_chat(pid,{'text':'Second message'},req(),(owner,None),db)
    assert len(p.project_chat(pid,(owner,None),db)['messages'])==2


def test_delete_project_removes_extras_without_deleting_source(data):
    db,owner,*_=data
    pid=create(data)
    p.add_manual_bill(pid,{'merchant':'Parking','amount':'2.00','currency':'RON',
        'participants':[{'user_id':owner.id}]},(owner,None),db)
    assert p.delete_project(pid,(owner,None),db)['deleted']
    assert db.query(ProjectManualBill).filter_by(project_id=pid).count()==0
    assert db.query(ProjectExpenseShare).filter_by(project_id=pid).count()==0


def test_confirmed_manual_expense_cannot_be_removed_or_project_erased(data):
    db,owner,member,*_=data
    pid=create(data);join(db,pid,member.id)
    expense=p.add_manual_bill(pid,{'merchant':'Fuel','amount':'9.00','currency':'RON',
        'participants':[{'user_id':owner.id},{'user_id':member.id}]},(owner,None),db)
    p.settle_project_share(pid,'manual',expense['id'],member.id,'report',(member,None),db)
    p.settle_project_share(pid,'manual',expense['id'],member.id,'confirm',(owner,None),db)
    with pytest.raises(HTTPException) as blocked:
        p.remove_project_item(pid,'manual',expense['id'],(owner,None),db)
    assert blocked.value.status_code==409
    with pytest.raises(HTTPException) as blocked:
        p.delete_project(pid,(owner,None),db)
    assert blocked.value.status_code==409


def test_smart_settle_toggle_preserves_source_record(data):
    db,owner,member,_,receipts,*_=data
    pid=create(data)
    s=receipts[0][1]
    p.add_project_items(pid,{'items':[{'kind':'split','source_id':s.id}]},(owner,None),db)
    p.accept_project(pid,(member,None),db)
    before=p.project_detail(pid,(owner,None),db)
    p.update_project_options(pid,{'smart_settle':False},(owner,None),db)
    after=p.project_detail(pid,(owner,None),db)
    assert before['currencies']==after['currencies']
    assert db.get(type(s),s.id).id==s.id
