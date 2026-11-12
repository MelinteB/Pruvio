"""Isolated v7.1.48 Project balance and reminder regression tests; no live DB."""
from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException
from test_bill_projects_v7141 import data, create
from app.react_app import bill_projects_v7141 as projects
from app.react_app.inbox import destination, messages
from app.models.group_project_v7141 import BillProjectMember
from app.models.push_notification import PushEvent


def join(db, project_id, user_id):
    projects.accept_project(project_id,(db.get(__import__('app.models.user',fromlist=['User']).User,user_id),None),db)


def test_summary_contains_all_accepted_members_and_source_amounts(data):
    db, owner, member, outsider, receipts, foreign, profile = data
    pid=create(data)
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':receipts[0][1].id},
        {'kind':'split','source_id':receipts[1][1].id}]},(owner,None),db)
    join(db,pid,member.id)
    summary=projects.project_detail(pid,(owner,None),db)
    rows={r['user_id']:r for r in summary['participant_balances']}
    assert owner.id in rows and member.id in rows
    debt=rows[member.id]
    assert set(debt['currencies'])=={'EUR','RON'}
    assert debt['currencies']['RON']['allocated']>0
    assert debt['currencies']['EUR']['outstanding']>0
    assert debt['can_remind'] is True
    assert {x['kind'] for x in debt['bills']}=={'split'}


def test_confirmation_changes_only_recipient_balance(data):
    db,owner,member,*_=data
    pid=create(data)
    db.add(BillProjectMember(project_id=pid,user_id=member.id,status='joined'));db.commit()
    expense=projects.add_manual_bill(pid,{'merchant':'Groceries','amount':'10.01','currency':'RON',
        'mode':'amount','participants':[{'user_id':owner.id,'value':'5.01'},
                                      {'user_id':member.id,'value':'5.00'}]},(owner,None),db)
    def balance():
        return next(r for r in projects.project_detail(pid,(owner,None),db)['participant_balances'] if r['user_id']==member.id)['currencies']['RON']
    assert balance()['outstanding']==5
    projects.settle_project_share(pid,'manual',expense['id'],member.id,'report',(member,None),db)
    assert balance()['reported']==5 and balance()['outstanding']==5
    assert next(r for r in projects.project_detail(pid,(owner,None),db)['participant_balances'] if r['user_id']==member.id)['can_remind'] is False
    projects.settle_project_share(pid,'manual',expense['id'],member.id,'confirm',(owner,None),db)
    assert balance()['confirmed']==5 and balance()['outstanding']==0
    assert projects.project_detail(pid,(owner,None),db)['project_settled'] is True


def test_reminder_owner_only_throttle_and_inbox_link(data):
    db,owner,member,outsider,receipts,*_=data
    pid=create(data)
    projects.add_project_items(pid,{'items':[{'kind':'split','source_id':receipts[0][1].id}]},(owner,None),db)
    with pytest.raises(HTTPException):projects.remind_project_participant(pid,member.id,(outsider,None),db)
    with pytest.raises(HTTPException):projects.remind_project_participant(pid,member.id,(owner,None),db)
    join(db,pid,member.id)
    sent=projects.remind_project_participant(pid,member.id,(owner,None),db)
    assert sent['queued'] and sent['outstanding'][0]['currency']=='RON'
    event=db.query(PushEvent).filter_by(id=sent['event_id']).one()
    assert event.kind=='project_reminder' and event.url==f'/projects/{pid}?view=settlement'
    assert 'iban' not in event.body.lower() and 'https://' not in event.body
    assert destination(db,member.id,event.url)==event.url
    assert destination(db,outsider.id,event.url) is None
    assert any(e['can_open'] for e in messages(unread=False,offset=0,identity=(member,None),db=db)['rows'])
    with pytest.raises(HTTPException) as ex:
        projects.remind_project_participant(pid,member.id,(owner,None),db)
    assert ex.value.status_code==429
    event.created_at=datetime.utcnow()-timedelta(hours=2);db.commit()
    assert projects.remind_project_participant(pid,member.id,(owner,None),db)['queued']


def test_revocation_prevents_notifications_opening(data):
    db,owner,member,*_=data
    pid=create(data)
    db.add(BillProjectMember(project_id=pid,user_id=member.id,status='joined'));db.commit()
    assert destination(db,member.id,f'/projects/{pid}?view=settlement')
    db.query(BillProjectMember).filter_by(project_id=pid,user_id=member.id).update({'status':'revoked'})
    db.commit()
    assert destination(db,member.id,f'/projects/{pid}?view=settlement') is None
    assert destination(db,member.id,'/projects/0?view=settlement') is None
    assert destination(db,member.id,'//evil.site') is None
