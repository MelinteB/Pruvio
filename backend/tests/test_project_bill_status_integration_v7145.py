"""Regression for one-time receipt allocation and payment-highlight lifecycle.

Uses the established isolated SQLite `data` fixture from v7.1.41; never use a
staging or production DB to execute these tests.
"""
from datetime import datetime
import pytest
from fastapi import HTTPException
from test_bill_projects_v7141 import data, create
from app.models.group_project_v7141 import BillProjectMember
from app.react_app import bill_projects_v7141 as projects


def test_receipt_highlight_and_prevent_repeat_allocation(data):
    db,owner,member,_,receipts,*_=data
    pid=create(data)
    db.add(BillProjectMember(project_id=pid,user_id=member.id,status='joined',joined_at=datetime.utcnow()))
    db.commit()
    case,_,_=receipts[0]
    projects.add_project_items(pid,{'items':[{'kind':'receipt','source_id':case.id}]},(owner,None),db)
    def entry():
        return next(x for x in projects.project_detail(pid,(owner,None),db)['items']
                    if x['kind']=='receipt' and x['source_id']==case.id)
    assert entry()['bill_state']=='unallocated'
    assert entry()['allocation_complete'] is False
    options={'mode':'equal','participants':[{'user_id':owner.id},{'user_id':member.id}]}
    projects.allocate_imported_receipt(pid,case.id,options,(owner,None),db)
    assert entry()['bill_state']=='allocated'
    assert entry()['payment_confirmed'] is False
    with pytest.raises(HTTPException) as err:
        projects.allocate_imported_receipt(pid,case.id,options,(owner,None),db)
    assert err.value.status_code==409
    projects.settle_project_share(pid,'receipt',case.id,member.id,'report',(member,None),db)
    assert entry()['bill_state']=='allocated'
    projects.settle_project_share(pid,'receipt',case.id,member.id,'confirm',(owner,None),db)
    assert entry()['bill_state']=='confirmed'
    assert entry()['payment_confirmed'] is True
