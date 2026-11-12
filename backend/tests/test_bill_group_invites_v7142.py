"""Group invite and exact-cent settlement regression; in-memory DB only."""
from datetime import datetime, timedelta
import hashlib
import pytest
from fastapi import HTTPException
from test_bill_projects_v7141 import data, create
from app.models.group_project_invite_v7142 import BillProjectInvite
from app.models.group_project_v7141 import BillProjectMember
from app.react_app import bill_projects_v7141 as groups
from app.services.group_settlement_v7142 import settlement_plan


def test_group_invite_follows_split_bill_link_pattern_without_plaintext_storage(data):
    db, owner, joined, outsider, receipts, *_=data
    pid=create(data)
    link=groups.create_invitation_link(pid,identity=(owner,None),db=db)
    assert link['requires_acceptance'] is True
    assert link['path']=='/projects/join/'+link['token']
    assert len(link['token'])>=40
    assert db.query(BillProjectInvite).filter_by(token_hash=hashlib.sha256(link['token'].encode()).hexdigest()).count()==1
    assert link['token'] not in repr(db.query(BillProjectInvite).first().__dict__)
    preview=groups.invitation_preview(link['token'],identity=(outsider,None),db=db)
    assert preview['name']=='Ski Trip'
    assert preview['membership_status'] is None
    assert len(preview)==5  # No members, balances or bank details exposed before acceptance.
    with pytest.raises(HTTPException) as invalid:
        groups.project_detail(pid,identity=(outsider,None),db=db)
    assert invalid.value.status_code==404
    result=groups.accept_invitation_link(link['token'],identity=(outsider,None),db=db)
    assert result['status']=='joined' and not result['already_member']
    assert groups.project_detail(pid,identity=(outsider,None),db=db)['id']==pid
    assert groups.accept_invitation_link(link['token'],identity=(outsider,None),db=db)['already_member']
    assert db.query(BillProjectMember).filter_by(project_id=pid,user_id=outsider.id).count()==1


def test_invitation_issue_revoke_owner_only_and_expiry(data):
    db, owner, other, outsider, *_=data
    pid=create(data)
    with pytest.raises(HTTPException) as forbidden:
        groups.create_invitation_link(pid,identity=(outsider,None),db=db)
    assert forbidden.value.status_code==404
    link=groups.create_invitation_link(pid,identity=(owner,None),db=db)
    old=link['token']
    assert groups.revoke_invitation_links(pid,identity=(owner,None),db=db)['revoked']==1
    with pytest.raises(HTTPException) as revoked:
        groups.invitation_preview(old,identity=(outsider,None),db=db)
    assert revoked.value.status_code==404
    renewed=groups.create_invitation_link(pid,identity=(owner,None),db=db)
    record=db.query(BillProjectInvite).filter_by(token_hash=hashlib.sha256(renewed['token'].encode()).hexdigest()).one()
    record.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    with pytest.raises(HTTPException) as expired:
        groups.accept_invitation_link(renewed['token'],identity=(outsider,None),db=db)
    assert expired.value.status_code==404
    assert db.query(BillProjectMember).filter_by(project_id=pid,user_id=outsider.id).count()==0


def test_invitation_acceptance_requires_capacity(data):
    db, owner, other, outsider, *_=data
    pid=create(data)
    link=groups.create_invitation_link(pid,identity=(owner,None),db=db)
    record=db.query(BillProjectInvite).filter_by(token_hash=hashlib.sha256(link['token'].encode()).hexdigest()).one()
    record.uses=record.max_uses;db.commit()
    with pytest.raises(HTTPException) as err:
        groups.accept_invitation_link(link['token'],identity=(outsider,None),db=db)
    assert err.value.status_code==404


def test_group_netting_reduces_reciprocal_debt_and_keeps_currencies_separate():
    debts=[{'payer_id':2,'payee_id':1,'currency':'RON','cents':1200},
           {'payer_id':1,'payee_id':2,'currency':'RON','cents':300},
           {'payer_id':2,'payee_id':1,'currency':'EUR','cents':503},
           {'payer_id':3,'payee_id':1,'currency':'RON','cents':300}]
    result=settlement_plan(debts,{1,2},{1:'Owner',2:'Member'})
    assert result['suggested_settlements']==[
       {'from_user_id':2,'from_name':'Member','to_user_id':1,'to_name':'Owner',
        'currency':'EUR','amount_minor':503,'amount':5.03},
       {'from_user_id':2,'from_name':'Member','to_user_id':1,'to_name':'Owner',
        'currency':'RON','amount_minor':900,'amount':9.0},
    ]
    assert result['excluded_nonmember_minor']=={'RON':300}
    assert sum(row['net_minor'] for row in result['net_balances'] if row['currency']=='RON')==0


def test_group_plan_reads_actual_split_payment_status_and_only_accepted_members(data):
    db,owner,member,outsider,receipts,*_=data
    pid=create(data)
    session=receipts[0][1]
    groups.add_project_items(pid,{'items':[{'kind':'split','source_id':session.id}]},(owner,None),db)
    summary=groups.project_detail(pid,(owner,None),db)
    assert summary['suggested_settlements']==[]
    assert summary['excluded_nonmember_minor']['RON']>0
    groups.accept_project(pid,(member,None),db)
    summary=groups.project_detail(pid,(owner,None),db)
    assert len(summary['suggested_settlements'])==1
    assert summary['suggested_settlements'][0]['currency']=='RON'
    receipts[0][2].payment_status='received';db.commit()
    summary=groups.project_detail(pid,(owner,None),db)
    assert summary['suggested_settlements']==[]


def test_netting_rejects_negative_or_fractional_minor_units():
    for cents in (-5, 0.5):
        with pytest.raises(ValueError):
            settlement_plan([{'payer_id':1,'payee_id':2,'currency':'RON','cents':cents}],{1,2},{})
