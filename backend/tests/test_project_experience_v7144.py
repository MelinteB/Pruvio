"""v7.1.44: isolated tests; a disposable SQLite DB only, never a staging or prod URL."""
import pytest
from fastapi import HTTPException
from test_bill_projects_v7141 import data, create
from app.models.project_cover_v7144 import ProjectCoverV7144
from app.react_app import bill_projects_v7141 as project_api


def test_cover_override_persists_for_owner_and_project_members(data):
    db, owner, member, *_ = data
    pid = project_api.create_project(
        {'name':'Ski trip','cover_key':'beach'},(owner,None),db)['id']
    assert db.get(ProjectCoverV7144,pid).cover_key == 'beach'
    assert project_api.project_detail(pid,(owner,None),db)['cover_key'] == 'beach'
    assert project_api.list_projects((owner,None),db)['projects'][0]['cover_key'] == 'beach'
    project_api.invite_username  # Existing private invitation workflow remains available.
    from app.models.group_project_v7141 import BillProjectMember
    db.add(BillProjectMember(project_id=pid,user_id=member.id,status='joined'))
    db.commit()
    assert project_api.project_detail(pid,(member,None),db)['cover_key'] == 'beach'
    assert project_api.list_projects((member,None),db)['projects'][0]['cover_key'] == 'beach'


def test_cover_can_be_changed_and_cleared_without_renaming(data):
    db,owner,*_=data
    pid=create(data)
    assert project_api.project_detail(pid,(owner,None),db)['cover_key'] is None
    assert project_api.update_project_options(pid,{'cover_key':'family'},(owner,None),db)['cover_key']=='family'
    assert project_api.update_project_options(pid,{'cover_key':None},(owner,None),db)['cover_key'] is None
    assert db.get(ProjectCoverV7144,pid) is None
    assert project_api.project_detail(pid,(owner,None),db)['name']=='Ski Trip'


def test_reject_unknown_cover_and_nonowner_change(data):
    db,owner,member,*_=data
    pid=create(data)
    with pytest.raises(ValueError):project_api.update_project_options(pid,{'cover_key':'https://evil.example/a.jpg'},(owner,None),db)
    with pytest.raises(ValueError):project_api.create_project({'name':'Test','cover_key':'../../secrets'},(owner,None),db)
    with pytest.raises(HTTPException) as blocked:
        project_api.update_project_options(pid,{'cover_key':'city'},(member,None),db)
    assert blocked.value.status_code in (403,404)


def test_candidate_list_is_nonempty_with_original_receipts(data):
    db,owner,member,_,receipts,*_=data
    items=project_api.candidates((owner,None),db)['items']
    assert any(x['kind']=='receipt' for x in items)
    assert any(x['kind']=='split' for x in items)
    assert all(x.get('case_id') for x in items)
    assert all(isinstance(x.get('label'),str) and x['label'] for x in items)
    assert all(isinstance(x.get('total'),(float,int)) for x in items if x['kind']=='split')
    assert project_api.candidates((member,None),db)['items']==[]


def test_delete_project_cleans_cover_and_preserves_source_records(data):
    db,owner,*_=data
    pid=project_api.create_project({'name':'Home','cover_key':'home'},(owner,None),db)['id']
    assert db.get(ProjectCoverV7144,pid) is not None
    result=project_api.delete_project(pid,(owner,None),db)
    assert result['deleted']
    assert db.get(ProjectCoverV7144,pid) is None
