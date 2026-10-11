from datetime import datetime
import re
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import Column,Integer,String,DateTime,and_,or_,exists
from app.db.database import Base,get_db
from app.models.push_notification import PushEvent
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.react_app.auth import current

class PruvsInboxRead(Base):
    __tablename__='pruvs_inbox_reads'
    user_id=Column(Integer,primary_key=True)
    event_id=Column(String(64),primary_key=True)
    read_at=Column(DateTime,nullable=False,default=datetime.utcnow)

router=APIRouter(prefix='/api/v1/inbox')
KINDS=('split_settled','split_reopened','reminder','bill_settled','bill_reopened')

def incoming(db,uid):
    # Includes historical v6.12 kind names. Current membership is checked on opening.
    own=exists().where(and_(SplitBillSession.owner_user_id==uid,or_(PushEvent.url=='/bill/'+SplitBillSession.token,PushEvent.url=='/split-bill/sessions/'+SplitBillSession.token+'/join',PushEvent.url=='/split-bill/sessions/'+SplitBillSession.token+'/widget-ui')))
    return db.query(PushEvent).filter(PushEvent.user_id==uid,PushEvent.kind.in_(KINDS),~own)

def mark(db,uid,e):
    if db.get(PruvsInboxRead,(uid,e.id)) is None:db.add(PruvsInboxRead(user_id=uid,event_id=e.id))
    e.read_at=datetime.utcnow()

def destination(db,uid,url):
    match=re.fullmatch(r'/(?:bill/|split-bill/sessions/)([A-Za-z0-9_-]{4,128})(?:/join|/widget-ui)?',url or '')
    if not match:return None
    s=db.query(SplitBillSession).filter_by(token=match.group(1)).first()
    if not s:return None
    member=db.query(SplitBillParticipant).filter_by(session_id=s.id,user_id=uid,status='joined').first()
    return '/bill/'+s.token if member else None

@router.get('')
def messages(unread:bool=False,offset:int=Query(0,ge=0),identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id;q=incoming(db,uid)
    q=q.outerjoin(PruvsInboxRead,and_(PruvsInboxRead.user_id==uid,PruvsInboxRead.event_id==PushEvent.id))
    unread_filter=and_(PruvsInboxRead.event_id.is_(None),PushEvent.read_at.is_(None))
    unread_count=q.filter(unread_filter).count()
    if unread:q=q.filter(unread_filter)
    total=q.count();rows=q.order_by(PushEvent.created_at.desc(),PushEvent.id.desc()).offset(offset).limit(30).all()
    result=[]
    for e in rows:
        # Old releases sent an owner's own transition back to them. Hide those.
        target=destination(db,uid,e.url)
        if e.kind in ('bill_settled','bill_reopened') and target:
            s=db.query(SplitBillSession).filter_by(token=target.split('/')[-1]).first()
            if s.owner_user_id==uid:continue
        result.append({'id':e.id,'title':e.title,'body':e.body,'kind':e.kind,'created_at':e.created_at,'read':bool(e.read_at or db.get(PruvsInboxRead,(uid,e.id))),'can_open':bool(target)})
    return {'rows':result,'total':total,'unread_count':unread_count}

@router.post('/read-all')
def read_all(identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id
    for e in incoming(db,uid).all():mark(db,uid,e)
    db.commit();return {'ok':True}

@router.post('/{eid}/read')
def read_one(eid:str,body:dict,identity=Depends(current),db=Depends(get_db)):
    uid=identity[0].id;e=incoming(db,uid).filter(PushEvent.id==eid).first()
    if not e:raise HTTPException(404,'Message not found.')
    if body.get('read',True):mark(db,uid,e)
    else:
        e.read_at=None;row=db.get(PruvsInboxRead,(uid,eid))
        if row:db.delete(row)
    db.commit();return {'ok':True}
