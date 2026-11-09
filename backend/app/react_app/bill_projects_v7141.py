"""Shared projects: owner-controlled bill imports, participant opt-in, server-derived balances.

A receipt folder is not a shared project.  This router deliberately does not change
split allocations, payment confirmation, original receipt currency, or payout details.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import os
import secrets
import hashlib
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from app.db.database import get_db
from app.models.case import Case
from app.models.receipt_item import ReceiptItem
from app.models.user import User
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.payment_profile import PaymentProfile
from app.models.group_project_v7141 import BillProject, BillProjectItem, BillProjectMember
from app.models.group_project_invite_v7142 import BillProjectInvite
from app.services.group_settlement_v7142 import settlement_plan
from app.react_app.auth import current, limit
from app.usernames import username_key
from fastapi import Request
from app.react_app.bill_service import get_split_bill_session_summary

router = APIRouter(prefix='/api/v1/bill-projects', tags=['Shared bill projects'])


def enabled():
    if os.getenv('PRUVS_CORE_V7141_PROJECTS_ENABLED','false').lower()!='true':
        raise HTTPException(404, 'Projects are not enabled.')


def amount_minor(value):
    n = Decimal(str(value or 0))
    if not n.is_finite(): raise ValueError('Invalid bill amount.')
    return int((n * Decimal(100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def currency_code(value):
    val = str(value or 'RON').strip().upper()
    if not 3 <= len(val) <= 10 or not val.isalnum():
        raise ValueError('Unsupported currency on receipt.')
    return val


def owned_source(db, user_id, kind, source_id):
    if type(source_id) is not int or source_id < 1: raise ValueError('Invalid receipt or split identifier.')
    if kind == 'receipt':
        case = db.query(Case).filter_by(id=source_id, user_id=user_id).first()
        if case: return case
    elif kind == 'split':
        session = db.query(SplitBillSession).filter_by(id=source_id, owner_user_id=user_id).first()
        if session: return session
    else: raise ValueError('Select a receipt or split session.')
    raise HTTPException(404, 'You can only add receipts or split sessions you own.')


def membership(db, uid, project_id, *, joined_only=True):
    enabled()
    project = db.get(BillProject, project_id)
    member = db.query(BillProjectMember).filter_by(project_id=project_id, user_id=uid).first() if project else None
    if not project or not member or (joined_only and member.status not in ('owner','joined')):
        raise HTTPException(404, 'Project not found or invitation not accepted.')
    return project, member


def owner(db, uid, project_id):
    project, _ = membership(db, uid, project_id)
    if project.owner_user_id != uid: raise HTTPException(403, 'Only the project owner can change its bills.')
    return project


def linked_rows(db, pid):
    return db.query(BillProjectItem).filter_by(project_id=pid).order_by(BillProjectItem.id).all()


def _private_profile(db, member):
    """Share only the specific saved profile the user explicitly selected."""
    if member.payment_profile_id is None: return None
    p = db.query(PaymentProfile).filter_by(id=member.payment_profile_id, user_id=member.user_id).first()
    if not p: return None
    return {k: getattr(p,k) for k in ('id','label','recipient_name','iban','bank_name','bic','revolut_link','payment_note')}


def _project_summary(db, project, caller_id):
    members = db.query(BillProjectMember).filter_by(project_id=project.id).all()
    member_ids = {m.user_id for m in members}
    users = {u.id:u for u in db.query(User).filter(User.id.in_(member_ids)).all()} if member_ids else {}
    rows = linked_rows(db, project.id)
    # All monetary values accumulated as exact minor units, per original currency.
    totals = defaultdict(lambda: {'bill_total':0,'allocated':0,'unassigned':0,'confirmed':0,'reported':0})
    people = {}
    obligations = []
    items = []
    split_case_ids = set()
    for link in rows:
        if link.kind != 'split': continue
        session = db.get(SplitBillSession,link.source_id)
        if not session or session.owner_user_id != link.added_by_user_id: continue
        summary = get_split_bill_session_summary(db, session, ensure_translations=False)
        curr = currency_code(summary['currency'])
        split_case_ids.add(session.case_id)
        bucket=totals[curr]
        bucket['bill_total']+=amount_minor(summary['grand_total'])
        bucket['allocated']+=sum(amount_minor(p['total']) for p in summary['participants'])
        bucket['unassigned']+=amount_minor(summary['remaining_total'])
        items.append({'kind':'split','source_id':session.id,'case_id':session.case_id,
          'currency':curr,'total':summary['grand_total'],'status':session.status,
          'participants_count':len(summary['participants']), 'token':session.token,
          'unassigned':summary['remaining_total'],
          'added_by_user_id':link.added_by_user_id,'readable_by_me':(caller_id==session.owner_user_id or
          db.query(SplitBillParticipant.id).filter_by(session_id=session.id,user_id=caller_id,status='joined').first() is not None)})
        for p in summary['participants']:
            uid = p['user_id']
            key = f'user:{uid}' if uid else f'guest:{session.id}:{p["participant_id"]}'
            person = people.setdefault(key,{'key':key,'user_id':uid,'name':p['display_name'],
                        'totals':defaultdict(lambda:{'owed':0,'reported':0,'confirmed':0}),
                        'bill_count':0,'is_guest':uid is None,'pay_to':defaultdict(lambda:defaultdict(int))})
            if uid and uid in users: person['name']=users[uid].name or p['display_name']
            part_amount=amount_minor(p['total'])
            payment=(p['payment_status'] or 'unpaid').lower()
            figures=person['totals'][curr]
            figures['owed']+=part_amount
            if payment in ('paid','received'):
                figures['reported']+=part_amount
                bucket['reported']+=part_amount
            if payment=='received':
                figures['confirmed']+=part_amount
                bucket['confirmed']+=part_amount
            # Bill ownership identifies the payee; the group never auto-transfers money.
            if uid!=session.owner_user_id:
                remaining = max(0, part_amount - (part_amount if payment == 'received' else 0))
                person['pay_to'][curr][session.owner_user_id] += remaining
                obligations.append({'payer_id':uid,'payee_id':session.owner_user_id,
                                    'currency':curr,'cents':remaining})
            person['bill_count']+=1
    for link in rows:
        if link.kind!='receipt': continue
        case=db.get(Case,link.source_id)
        if not case or case.user_id != link.added_by_user_id: continue
        # Receipt already represented by a linked split must not count twice.
        included = case.id in split_case_ids
        all_items=db.query(ReceiptItem).filter_by(case_id=case.id).all()
        currencies=defaultdict(int)
        for line in all_items:
            curr=currency_code(line.currency)
            val=amount_minor(line.total_price)
            currencies[curr]+=val
            if not included:
                totals[curr]['bill_total']+=val
                totals[curr]['unassigned']+=val
        items.append({'kind':'receipt','source_id':case.id,'case_id':case.id,
            'currency':next(iter(currencies), 'RON') if len(currencies)==1 else 'MULTI',
            'total':sum(currencies.values())/100 if len(currencies)==1 else None,
            'totals_by_currency':{key:value/100 for key,value in currencies.items()},
            'also_linked_as_split':included,'status':case.status,
            'added_by_user_id':link.added_by_user_id,'readable_by_me':caller_id==case.user_id})
    member_rows=[]
    for m in members:
        # Protect against someone seeing payout info before accepting invitation.
        payment = _private_profile(db,m) if m.status in ('owner','joined') else None
        member_rows.append({'user_id':m.user_id,'name':(users[m.user_id].name or 'Member') if m.user_id in users else 'Member',
                 'status':m.status,'is_me':m.user_id==caller_id,
                 'payment_profile':payment})
    people_rows=[]
    for p in people.values():
        converted={currency:{k:v/100 for k,v in value.items()} |
            {'outstanding':(value['owed']-value['confirmed'])/100} for currency,value in p['totals'].items()}
        people_rows.append({'key':p['key'],'user_id':p['user_id'],'name':p['name'],
              'is_guest':p['is_guest'],'bill_count':p['bill_count'],
              'currencies':converted,
              'pay_to':[{ 'currency':curr,'user_id':payee,'recipient_name':(users[payee].name if payee in users else 'Bill owner'),
                  'outstanding':cents/100} for curr,payees in p['pay_to'].items() for payee,cents in payees.items() if cents>0]})
    buckets={currency:{k:round(val/100,2) for k,val in amount.items()} for currency,amount in totals.items()}
    joined_ids={m.user_id for m in members if m.status in ('owner','joined')}
    netting = settlement_plan(obligations, joined_ids,
                {uid:(u.name or 'Member') for uid,u in users.items()})
    return {'id':project.id,'name':project.name,'owner_user_id':project.owner_user_id,
         'is_owner':caller_id==project.owner_user_id,'members':member_rows,
         'items':items,'participants':people_rows,'currencies':buckets,
         **netting, 'receipt_only_amounts_are_unassigned':True,
         'payment_notice':'Reported payments are not confirmed until the recipient confirms them on the individual bill.'}


@router.get('')
def list_projects(identity=Depends(current), db=Depends(get_db)):
    enabled(); uid=identity[0].id
    rows=(db.query(BillProject,BillProjectMember)
          .join(BillProjectMember,BillProjectMember.project_id==BillProject.id)
          .filter(BillProjectMember.user_id==uid)
          .order_by(BillProject.created_at.desc()).all())
    return {'projects':[{'id':p.id,'name':p.name,'owner_user_id':p.owner_user_id,
              'membership_status':m.status,'created_at':p.created_at.isoformat()} for p,m in rows]}

@router.get('/candidates')
def candidates(identity=Depends(current),db=Depends(get_db)):
    enabled(); uid=identity[0].id
    cases=(db.query(Case).filter_by(user_id=uid).order_by(Case.created_at.desc()).limit(150).all())
    sessions=(db.query(SplitBillSession).filter_by(owner_user_id=uid)
              .order_by(SplitBillSession.created_at.desc()).limit(150).all())
    case_ids={c.id for c in cases} | {s.case_id for s in sessions}
    amounts=defaultdict(lambda:defaultdict(int))
    if case_ids:
        for line in db.query(ReceiptItem).filter(ReceiptItem.case_id.in_(case_ids)).all():
            amounts[line.case_id][currency_code(line.currency)]+=amount_minor(line.total_price)
    from app.react_app.receipt_labels import receipt_labels
    labels=receipt_labels(db,case_ids)
    return {'items':(
       [{'kind':'receipt','source_id':c.id,'label':labels.get(c.id,f'Receipt #{c.id}')+' · receipt #'+str(c.id),
         'date':c.created_at.isoformat() if c.created_at else '',
         'totals':{k:v/100 for k,v in amounts[c.id].items()}} for c in cases] +
       [{'kind':'split','source_id':s.id,'label':labels.get(s.case_id,f'Receipt #{s.case_id}')+' · split #'+str(s.id),
         'date':s.created_at.isoformat() if s.created_at else '',
         'currency':s.currency or 'RON','status':s.status} for s in sessions])}

@router.post('')
def create_project(body:dict,identity=Depends(current),db=Depends(get_db)):
    enabled();name=body.get('name')
    if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Project name must contain 1–100 characters.')
    project=BillProject(owner_user_id=identity[0].id,name=name.strip())
    db.add(project);db.flush()
    db.add(BillProjectMember(project_id=project.id,user_id=identity[0].id,status='owner',joined_at=datetime.utcnow()))
    db.commit()
    return {'id':project.id,'name':project.name}

# Invitation URL is intentionally not included in project details, notification payloads or logs.
_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{40,128}$')


def _valid_invitation(db, token):
    enabled()
    if not isinstance(token, str) or not _TOKEN_RE.fullmatch(token):
        raise HTTPException(404, 'Invitation unavailable.')
    digest = hashlib.sha256(token.encode('ascii')).hexdigest()
    invite = (db.query(BillProjectInvite).filter_by(token_hash=digest, active=True)
              .with_for_update().first())
    if (not invite or invite.expires_at <= datetime.utcnow() or
            invite.uses >= invite.max_uses):
        raise HTTPException(404, 'Invitation expired, revoked, or unavailable.')
    project = db.get(BillProject, invite.project_id)
    if project is None: raise HTTPException(404, 'Invitation unavailable.')
    return invite,project


@router.post('/{project_id}/invite-link')
def create_invitation_link(project_id:int,identity=Depends(current),db=Depends(get_db)):
    project = owner(db,identity[0].id,project_id)
    # Older links remain revocable and valid for up to 14 days; cap active issuance.
    outstanding = (db.query(BillProjectInvite).filter_by(project_id=project_id,active=True)
                   .order_by(BillProjectInvite.created_at, BillProjectInvite.id).all())
    for previous in outstanding[:-4]: previous.active = False
    raw = secrets.token_urlsafe(32)
    invite = BillProjectInvite(project_id=project.id,created_by_user_id=identity[0].id,
             token_hash=hashlib.sha256(raw.encode('ascii')).hexdigest(),
             expires_at=datetime.utcnow()+timedelta(days=14),max_uses=100,uses=0)
    db.add(invite);db.commit()
    return {'token':raw,'expires_at':invite.expires_at.isoformat(),
            'path':'/projects/join/'+raw,'requires_acceptance':True}


@router.post('/{project_id}/revoke-links')
def revoke_invitation_links(project_id:int,identity=Depends(current),db=Depends(get_db)):
    owner(db,identity[0].id,project_id)
    count = (db.query(BillProjectInvite).filter_by(project_id=project_id,active=True)
             .update({'active':False}, synchronize_session=False))
    db.commit()
    return {'revoked':count}


@router.get('/invitations/{token}')
def invitation_preview(token:str,identity=Depends(current),db=Depends(get_db)):
    invite,project=_valid_invitation(db,token)
    member=(db.query(BillProjectMember).filter_by(project_id=project.id,user_id=identity[0].id).first())
    return {'name':project.name,'project_id':project.id,
            'membership_status':member.status if member else None,
            'requires_acceptance':True,
            'expires_at':invite.expires_at.isoformat()}


@router.post('/invitations/{token}/accept')
def accept_invitation_link(token:str,identity=Depends(current),db=Depends(get_db)):
    invite,project=_valid_invitation(db,token)
    uid = identity[0].id
    member=(db.query(BillProjectMember).filter_by(project_id=project.id,user_id=uid)
            .with_for_update().first())
    if member and member.status in ('owner','joined'):
        return {'status':member.status,'project_id':project.id,'already_member':True}
    if not member:
        if db.query(BillProjectMember).filter_by(project_id=project.id).count() >= 100:
            raise HTTPException(409, 'Project member limit reached.')
        member=BillProjectMember(project_id=project.id,user_id=uid,status='joined',joined_at=datetime.utcnow())
        db.add(member)
    else:
        member.status='joined';member.joined_at=datetime.utcnow()
    invite.uses += 1
    db.commit()
    return {'status':'joined','project_id':project.id,'already_member':False}


@router.get('/{project_id}')
def project_detail(project_id:int,identity=Depends(current),db=Depends(get_db)):
    project,_=membership(db,identity[0].id,project_id)
    return _project_summary(db,project,identity[0].id)

@router.put('/{project_id}')
def rename_project(project_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    project=owner(db,identity[0].id,project_id);name=body.get('name')
    if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Project name must contain 1–100 characters.')
    project.name=name.strip();project.modified_at=datetime.utcnow();db.commit()
    return {'id':project.id,'name':project.name}

@router.delete('/{project_id}')
def delete_project(project_id:int,identity=Depends(current),db=Depends(get_db)):
    project=owner(db,identity[0].id,project_id)
    db.query(BillProjectInvite).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(BillProjectItem).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(BillProjectMember).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.delete(project);db.commit()
    return {'deleted':True,'original_receipts_and_splits_preserved':True}

@router.post('/{project_id}/items')
def add_project_items(project_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    enabled(); uid=identity[0].id
    project,_=membership(db,uid,project_id)
    raw=body.get('items')
    if not isinstance(raw,list) or not 1<=len(raw)<=100:raise ValueError('Select 1–100 saved receipts or split sessions.')
    selected=set();sessions=[]
    for entry in raw:
        if not isinstance(entry,dict):raise ValueError('Invalid project entry.')
        kind=entry.get('kind');source_id=entry.get('source_id')
        obj=owned_source(db,uid,kind,source_id)
        selected.add((kind,source_id))
        if kind=='split':sessions.append(obj)
    existing={(row.kind,row.source_id) for row in linked_rows(db,project_id)}
    if len(existing|selected)>300:raise ValueError('Project limit: 300 items.')
    # One receipt may have multiple historical split sessions. Reject double-counting.
    linked_splits=[db.get(SplitBillSession,sid) for kind,sid in existing|selected if kind=='split']
    linked_case_ids=[split.case_id for split in linked_splits if split is not None]
    if len(linked_case_ids)!=len(set(linked_case_ids)):
        raise ValueError('Only one split session per receipt can be linked to a project.')
    for kind,sid in selected-existing:
        db.add(BillProjectItem(project_id=project_id,added_by_user_id=uid,kind=kind,source_id=sid))
    # Every registered joined participant is invited, but not silently opted in.
    linked_members={m.user_id for m in db.query(BillProjectMember).filter_by(project_id=project_id).all()}
    invited=set()
    for session in sessions:
        for (member_uid,) in db.query(SplitBillParticipant.user_id).filter_by(session_id=session.id,status='joined').all():
            if member_uid and member_uid not in linked_members and member_uid!=uid:
                invited.add(member_uid)
    for member_uid in invited:
        db.add(BillProjectMember(project_id=project_id,user_id=member_uid,status='invited'))
    project.modified_at=datetime.utcnow();db.commit()
    return {'added':len(selected-existing),'new_invitations':len(invited),'requires_invitation_acceptance':True}

@router.delete('/{project_id}/items/{kind}/{source_id}')
def remove_project_item(project_id:int,kind:str,source_id:int,identity=Depends(current),db=Depends(get_db)):
    project,_=membership(db,identity[0].id,project_id)
    if kind not in ('receipt','split'): raise ValueError('Unknown project item type.')
    row=db.query(BillProjectItem).filter_by(project_id=project_id,kind=kind,source_id=source_id).first()
    if row and row.added_by_user_id not in (identity[0].id,) and project.owner_user_id!=identity[0].id:
        raise HTTPException(403,'Only the contributor or project owner can remove this entry.')
    changed=0
    if row: db.delete(row);changed=1
    db.commit();return {'removed':bool(changed),'original_record_unchanged':True}

@router.post('/{project_id}/invite')
def invite_username(project_id:int,body:dict,request:Request,identity=Depends(current),db=Depends(get_db)):
    enabled()
    project=owner(db,identity[0].id,project_id)
    limit(db,request,'project-member-invite',20)
    raw=body.get('username')
    if not isinstance(raw,str):raise ValueError('Enter a registered Pruvs username.')
    target=db.query(User).filter_by(username_key=username_key(raw),status='active').first()
    if not target:raise HTTPException(404,'Active Pruvs account not found for that username.')
    if target.id==project.owner_user_id:raise ValueError('Project owner is already a member.')
    existing=db.query(BillProjectMember).filter_by(project_id=project_id,user_id=target.id).first()
    if existing:return {'invited':False,'membership_status':existing.status}
    if db.query(BillProjectMember).filter_by(project_id=project_id).count()>=100:
        raise ValueError('Maximum 100 project members.')
    db.add(BillProjectMember(project_id=project_id,user_id=target.id,status='invited'))
    db.commit()
    return {'invited':True,'membership_status':'invited'}

@router.delete('/{project_id}/members/{member_user_id}')
def remove_project_member(project_id:int,member_user_id:int,identity=Depends(current),db=Depends(get_db)):
    project=owner(db,identity[0].id,project_id)
    if member_user_id==project.owner_user_id:raise HTTPException(403,'Project owner cannot be removed.')
    target=db.query(BillProjectMember).filter_by(project_id=project.id,user_id=member_user_id).first()
    if not target:raise HTTPException(404,'Project member not found.')
    # Never keep sharing records contributed by a user after access is revoked.
    removed=db.query(BillProjectItem).filter_by(project_id=project.id,added_by_user_id=member_user_id).delete(synchronize_session=False)
    db.delete(target);db.commit();return {'revoked':True,'contributed_links_removed':removed}

@router.post('/{project_id}/leave')
def leave_project(project_id:int,identity=Depends(current),db=Depends(get_db)):
    project,member=membership(db,identity[0].id,project_id)
    if project.owner_user_id==identity[0].id:
        raise HTTPException(403,'Transfer or delete a project you own instead.')
    removed=db.query(BillProjectItem).filter_by(project_id=project.id,added_by_user_id=identity[0].id).delete(synchronize_session=False)
    db.delete(member);db.commit();return {'left':True,'contributed_links_removed':removed}

@router.post('/{project_id}/sync-participants')
def sync_participants(project_id:int,identity=Depends(current),db=Depends(get_db)):
    project,_=membership(db,identity[0].id,project_id)
    session_ids=[row.source_id for row in linked_rows(db,project_id) if row.kind=='split']
    if not session_ids: return {'new_invitations':0}
    existing={m.user_id for m in db.query(BillProjectMember).filter_by(project_id=project_id).all()}
    joined={uid for (uid,) in db.query(SplitBillParticipant.user_id).filter(
              SplitBillParticipant.session_id.in_(session_ids),SplitBillParticipant.status=='joined').all() if uid}
    newcomers=joined-existing
    for uid in newcomers:
        db.add(BillProjectMember(project_id=project.id,user_id=uid,status='invited'))
    db.commit()
    return {'new_invitations':len(newcomers),'requires_invitation_acceptance':True}

@router.post('/{project_id}/accept')
def accept_project(project_id:int,identity=Depends(current),db=Depends(get_db)):
    enabled(); uid=identity[0].id
    project,member=membership(db,uid,project_id,joined_only=False)
    if member.status=='invited':
        member.status='joined';member.joined_at=datetime.utcnow();db.commit()
    return {'status':member.status,'id':project.id}

@router.post('/{project_id}/decline')
def decline_project(project_id:int,identity=Depends(current),db=Depends(get_db)):
    enabled();uid=identity[0].id
    _,member=membership(db,uid,project_id,joined_only=False)
    if member.status=='owner':raise HTTPException(403,'Owner cannot decline their project.')
    db.delete(member);db.commit();return {'declined':True}

@router.put('/{project_id}/payment-profile')
def share_payment_profile(project_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    _,member=membership(db,identity[0].id,project_id)
    profile_id=body.get('payment_profile_id')
    if profile_id is not None:
        if type(profile_id) is not int or profile_id<1:raise ValueError('Invalid payment profile.')
        if not db.query(PaymentProfile.id).filter_by(id=profile_id,user_id=identity[0].id).first():
            raise HTTPException(404,'Your payment profile was not found.')
    member.payment_profile_id=profile_id;db.commit()
    return {'shared':profile_id is not None}
