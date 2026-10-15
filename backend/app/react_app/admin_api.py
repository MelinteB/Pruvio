import csv
import io
import json
import secrets
import os
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException,Query,Response,Header
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import ValidationError
from sqlalchemy import cast,String,or_,inspect,Column,Integer,DateTime,Text,Float,Boolean
from app.db.database import get_db,Base
from app.models.user import User
from app.models.document import Document
from app.services import admin_dashboard_service as d
from app.react_app.auth import admin,revoke_user

router=APIRouter(prefix='/api/v1/admin')
legacy_router=APIRouter(prefix='/admin/user-controls',tags=['Admin - User Controls'])
class AdminUserAction(Base):
    __tablename__='pruvs_admin_user_actions'
    id=Column(Integer,primary_key=True)
    performed_at=Column(DateTime(timezone=True),default=datetime.utcnow,nullable=False)
    actor_id=Column(Integer,nullable=True)
    user_id=Column(Integer,nullable=False)
    action=Column(String(32),nullable=False)
    before_status=Column(String(32))
    after_status=Column(String(32))
    reason=Column(Text)

# Never export push subscriptions, pending confirmation secrets or session credentials.
d.EDITABLE['users'].discard('status')  # Status changes use audited account controls.
d.HIDDEN.update({'subscription','endpoint_hash','grant_hash','test_hash','confirmation','lease_token','csrf_hash','binding_hash','challenge','idempotency_key'})
d.SECURITY_FIELDS.update({
 'pruvs_react_sessions':{'user_id','expires_at','created_at'},
 'pruvs_react_challenges':{'purpose','user_id','expires_at'},
 'pruvs_react_rate_limits':{'count','reset_at'},
 'pruvs_push_grants':{'user_id','expires_at','active'},
 'pruvs_push_devices':{'id','user_id','label','active','confirmed_at','last_test_at','updated_at'},
})


def model_info(entity):
    model=d.model_for(entity);pk=inspect(model).primary_key[0]
    columns=d.visible_columns(model)
    # Security records without a visible primary key are summarized only.
    return model,pk,columns

def key_value(pk,value):
    try:return pk.type.python_type(value)
    except (ValueError,TypeError):raise HTTPException(404,'Record not found.')

@router.get('/catalog')
def catalog(identity=Depends(admin),db=Depends(get_db)):
    result=[]
    for row in d.catalog(db,identity[0].id):
        model,pk,cols=model_info(row['key'])
        row['pk']=pk.name if len(inspect(model).primary_key)==1 and pk.name in [c.name for c in cols] else None
        row['fields']=[{'name':c.name,'type':str(c.type),'nullable':c.nullable,'editable':c.name in d.EDITABLE.get(row['key'],set())} for c in cols]
        result.append(row)
    return result


def filtered(db,entity,q,field,value):
    model,pk,cols=model_info(entity);query=db.query(model)
    if q:
        escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        searchable=[c for c in cols if isinstance(c.type,(String,Text,Integer,Float,Boolean,DateTime))]
        if searchable:query=query.filter(or_(*[cast(c,String).ilike('%'+escaped+'%',escape='\\') for c in searchable]))
    if field:
        column=next((c for c in cols if c.name==field),None)
        if column is None:raise ValueError('Invalid filter field.')
        query=query.filter(cast(column,String)==value)
    return query,pk,cols

@router.get('/records/{entity}')
def records(entity:str,q:str='',offset:int=Query(0,ge=0),field:str='',value:str='',include_deleted:bool=False,identity=Depends(admin),db=Depends(get_db)):
    query,pk,cols=filtered(db,entity,q,field,value)
    if entity=='users' and not include_deleted:query=query.filter(User.status!='deleted')
    return {'total':query.count(),'rows':[d.serialize(r) for r in query.order_by(pk.desc()).offset(offset).limit(25)]}

@router.get('/records/{entity}/export')
def export(entity:str,q:str='',field:str='',value:str='',identity=Depends(admin),db=Depends(get_db)):
    query,pk,cols=filtered(db,entity,q,field,value)
    if query.count()>10000:raise ValueError('Narrow the filter to 10,000 records or fewer.')
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=[c.name for c in cols]);writer.writeheader()
    for row in query.order_by(pk).yield_per(100):
        writer.writerow({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in d.serialize(row).items()})
    d.add_audit(db,identity[0].id,'react','export',entity,None);db.commit()
    return Response(output.getvalue().encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="pruvs-{entity}.csv"'})

@router.get('/records/{entity}/{record_id}')
def record(entity:str,record_id:str,identity=Depends(admin),db=Depends(get_db)):
    model,pk,cols=model_info(entity)
    if len(inspect(model).primary_key)!=1 or pk.name not in [c.name for c in cols]:raise HTTPException(403,'Security record details are restricted.')
    key=key_value(pk,record_id);row=db.get(model,key)
    if not row:raise HTTPException(404,'Record not found.')
    return {'record':d.serialize(row),'revision':d.revision(row),'related':d.related_records(db,identity[0].id,entity,key)}

@router.patch('/records/{entity}/{record_id}')
def update(entity:str,record_id:int,body:dict,identity=Depends(admin),db=Depends(get_db)):
    try:d.update_record(db,identity[0].id,entity,record_id,body.get('changes',{}),body.get('revision',''))
    except ValidationError as exc:raise HTTPException(400,'Please check the account fields and try again.') from exc
    if entity=='users':
        u=db.get(User,record_id)
        if u and u.status!='active':revoke_user(db,u.id);db.commit()
    return {'ok':True}

@router.get('/users/{uid}/bills')
def user_bills(uid:int,offset:int=Query(0,ge=0),identity=Depends(admin),db=Depends(get_db)):
    total,rows=d.list_user_bills(db,identity[0].id,uid,offset=offset);return {'total':total,'rows':rows}

@router.get('/users/{uid}/bills/{cid}')
def user_bill(uid:int,cid:int,identity=Depends(admin),db=Depends(get_db)):
    return d.user_bill_details(db,identity[0].id,uid,cid)

@router.post('/users/{uid}/{action}')
def user_action(uid:int,action:str,body:dict,identity=Depends(admin),db=Depends(get_db)):
    if str(body.get('confirm',''))!=str(uid):raise ValueError('Type the user ID to confirm.')
    return change_user(db,uid,action,identity[0].id,str(body.get('reason',''))[:500])

def change_user(db,uid,action,actor_id=None,reason=''):
    # Serialize administrator status changes, including last-administrator checks.
    db.query(User).filter_by(is_admin=True).order_by(User.id).with_for_update().all()
    target=db.query(User).filter_by(id=uid).with_for_update().first()
    if not target:raise HTTPException(404,'User not found.')
    if action not in ('block','unblock','delete'):raise ValueError('Invalid action.')
    if uid==actor_id:raise ValueError('You cannot block or delete your own account here.')
    if target.status=='deleted':raise ValueError('Deleted users cannot be changed.')
    if target.is_admin and action in ('block','delete') and db.query(User).filter_by(is_admin=True,status='active').count()<=1:raise ValueError('Cannot remove the last active administrator.')
    if action=='unblock' and target.status!='blocked':raise ValueError('Only blocked users can be unblocked.')
    previous=target.status
    target.status={'block':'blocked','unblock':'active','delete':'deleted'}[action]
    if action=='delete':
        target.name='Deleted user';target.email=f'deleted-{uid}@pruvs.invalid';target.username=f'deleted-{uid}'
        target.username_key=f'deleted-{uid}';target.phone_number=f'deleted-{uid}';target.password_hash=None
        target.is_email_verified=False;target.is_phone_verified=False
        for key in ('payment_recipient_name','payment_iban','payment_bank_name','payment_bic','revolut_payment_link','payment_note'):setattr(target,key,None)
    revoke_user(db,uid)
    d.add_audit(db,actor_id,'react' if actor_id else 'admin-control-api',action,'users',uid,['status'])
    db.add(AdminUserAction(actor_id=actor_id,user_id=uid,action=action,before_status=previous,after_status=target.status,reason=reason))
    db.commit();return {'ok':True,'id':uid,'previous_status':previous,'status':target.status,'operation':action}


def control_key(x_pruvs_admin_key:str|None=Header(default=None)):
    expected=os.getenv('PRUVS_ADMIN_CONTROL_KEY','')
    if not expected or not x_pruvs_admin_key or not secrets.compare_digest(expected,x_pruvs_admin_key):raise HTTPException(403,'Administrator authorization required.')

@legacy_router.get('/users',dependencies=[Depends(control_key)])
def control_users(db=Depends(get_db)):
    return [{'id':u.id,'display':u.name or u.username,'email':u.email,'status':u.status,'is_admin':u.is_admin} for u in db.query(User).order_by(User.id.desc()).limit(100)]

@legacy_router.post('/users/{uid}/{action}',dependencies=[Depends(control_key)])
def control_action(uid:int,action:str,body:dict,db=Depends(get_db)):
    if action not in ('block','unblock'):raise HTTPException(404,'Unknown action.')
    return change_user(db,uid,action,reason=str(body.get('reason',''))[:500])

@legacy_router.delete('/users/{uid}',dependencies=[Depends(control_key)])
def control_delete(uid:int,body:dict|None=None,db=Depends(get_db)):
    return change_user(db,uid,'delete',reason=str((body or {}).get('reason',''))[:500])

@legacy_router.get('/audit',dependencies=[Depends(control_key)])
def control_audit(db=Depends(get_db)):
    return [d.serialize(r) for r in db.query(AdminUserAction).order_by(AdminUserAction.id.desc()).limit(250)]


@router.get('/users/{uid}/bills/{cid}/export')
def bill_export(uid:int,cid:int,identity=Depends(admin),db=Depends(get_db)):
    result=d.user_bill_details(db,identity[0].id,uid,cid)
    d.add_audit(db,identity[0].id,'react','export','cases',cid,['bill_details']);db.commit()
    return Response(json.dumps(result,default=str,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="pruvs-user-{uid}-bill-{cid}.json"'})

@router.get('/users/{uid}/bills/{cid}/documents/{did}/file')
def bill_document(uid:int,cid:int,did:int,identity=Depends(admin),db=Depends(get_db)):
    # Check both the user's bill relationship and the document's case before opening a file.
    if not d.user_bill_query(db,uid).filter_by(id=cid).first():raise HTTPException(404,'Bill not found.')
    doc=db.query(Document).filter_by(id=did,case_id=cid).first()
    from app.services.document_service import resolve_document_path
    path=resolve_document_path(doc)
    if path is None:raise HTTPException(404,'The original file is unavailable on this server.')
    return FileResponse(path,media_type=doc.mime_type or 'application/octet-stream',
                        filename=doc.original_filename or doc.stored_filename,
                        content_disposition_type='inline',headers={'Cache-Control':'no-store'})

@router.get('/operational-overview')
def operational_overview(identity=Depends(admin),db=Depends(get_db)):
    from app.models.external_ocr_usage import ExternalOCRUsage
    from app.models.push_notification import PushEvent
    from app.models.case import Case
    now=datetime.utcnow();month=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    ocr=db.query(ExternalOCRUsage).filter(ExternalOCRUsage.created_at>=month)
    captured=db.query(Case).filter(Case.module=='split_bill',Case.created_at>=month)
    notifications=db.query(PushEvent).filter(PushEvent.created_at>=month)
    return {'month':month.strftime('%Y-%m'),'ocr_attempts':ocr.count(),
      'ocr_completed':captured.filter(Case.status.notin_(['processing','processing_failed'])).count(),
      'notification_events':notifications.count(),
      'notification_unread':notifications.filter(PushEvent.read_at.is_(None)).count(),
      'registered_users':db.query(User).filter(User.status!='deleted').count(),
      'receipts':db.query(Case).count(),
      'note':'OCR completions are processed receipt cases; attempts are external-provider log records. Notification events are not delivery confirmation.'}
