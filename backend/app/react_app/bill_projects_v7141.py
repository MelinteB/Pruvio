from app.services.project_bill_state_v7145 import split_state, project_share_state
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
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from app.models.case import Case
from app.models.receipt_item import ReceiptItem
from app.models.user import User
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.payment_profile import PaymentProfile
from app.models.group_project_v7141 import BillProject, BillProjectItem, BillProjectMember
from app.models.group_project_invite_v7142 import BillProjectInvite
from app.models.project_activity_v7143 import ProjectOptions, ProjectManualBill, ProjectExpenseShare, ProjectChatMessage
from app.models.project_cover_v7144 import ProjectCoverV7144
from app.services.project_allocations_v7143 import allocate_minor, to_minor
from app.services.group_settlement_v7142 import settlement_plan
from app.react_app.auth import current, limit
from app.usernames import username_key
from fastapi import Request
from app.react_app.bill_service import get_split_bill_session_summary

router = APIRouter(prefix='/api/v1/bill-projects', tags=['Shared bill projects'])

COVER_KEYS = frozenset({'mountain','beach','city','camping','family','party','home',
                        'roadtrip','food','work','sports','birthday','wedding','nature','default'})


def checked_cover(value):
    if not isinstance(value,str) or value not in COVER_KEYS:
        raise ValueError('Choose one of the available Project covers.')
    return value


def cover_of(db, project_id):
    stored = db.get(ProjectCoverV7144, project_id)
    return stored.cover_key if stored else None


def receipt_labels_safe(db, case_ids):
    if not case_ids: return {}
    try:
        from app.react_app.receipt_labels import receipt_labels
        return receipt_labels(db, case_ids)
    except ImportError:
        # Restricted offline regression env has no optional OCR dependencies.
        return {cid: f'Receipt #{cid}' for cid in case_ids}



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
    source_case_ids = set()
    completed = []
    pending_source_count = 0
    label_ids={db.get(SplitBillSession,x.source_id).case_id for x in rows if x.kind=="split" and db.get(SplitBillSession,x.source_id)} | {x.source_id for x in rows if x.kind=="receipt"}
    labels=receipt_labels_safe(db,label_ids)

    for link in rows:
        if link.kind != 'split': continue
        session = db.get(SplitBillSession,link.source_id)
        if not session or session.owner_user_id != link.added_by_user_id: continue
        summary = get_split_bill_session_summary(db, session, ensure_translations=False)
        curr = currency_code(summary['currency'])
        split_case_ids.add(session.case_id)
        source_case_ids.add(session.case_id)
        bucket=totals[curr]
        bucket['bill_total']+=amount_minor(summary['grand_total'])
        bucket['allocated']+=sum(amount_minor(p['total']) for p in summary['participants'])
        bucket['unassigned']+=amount_minor(summary['remaining_total'])
        completed.append(bool(summary['remaining_total'] < .005 and all(p['payment_status']=='received' or p['user_id']==session.owner_user_id or p['total'] < .005 for p in summary['participants'])))
        fx = None
        if session.fx_settings_json:
            try:
                import json
                quoted=json.loads(session.fx_settings_json)
                if quoted.get('base')==curr and quoted.get('target') and Decimal(str(quoted.get('rate'))) > 0:
                    fx={'currency':currency_code(quoted['target']),'rate':str(quoted['rate']),
                        'total':float((Decimal(str(summary['grand_total']))*Decimal(str(quoted['rate']))).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
                        'label':'FX reference only — original split remains payable in '+curr}
            except (ValueError,TypeError,ArithmeticError):pass
        split_display_state = split_state(summary['remaining_total'], summary['participants'], session.owner_user_id)
        items.append({'kind':'split','source_id':session.id,'case_id':session.case_id,
          'bill_state':split_display_state,'allocation_complete':split_display_state!='unallocated',
          'payment_confirmed':split_display_state=='confirmed',
          'merchant':labels.get(session.case_id,'Receipt #'+str(session.case_id)),
          'fx_reference':fx,
          'allocations':[{'user_id':p['user_id'],'name':p['display_name'],'amount':p['total'],'currency':curr,'payment_status':p['payment_status']} for p in summary['participants']],
          'paid_by_user_id':session.owner_user_id,'currency':curr,'total':summary['grand_total'],'status':session.status,
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
        allocated_rows=(db.query(ProjectExpenseShare).filter_by(project_id=project.id,kind='receipt',source_id=case.id).all())
        if allocated_rows and not included:
            if len(currencies)!=1:raise ValueError('Allocated receipt must use one currency.')
            only_currency=next(iter(currencies))
            subtotal=sum(x.amount_minor for x in allocated_rows)
            if subtotal!=currencies[only_currency]:raise ValueError('Incomplete project receipt allocation.')
            totals[only_currency]['allocated']+=subtotal
            totals[only_currency]['unassigned']-=subtotal
            for a in allocated_rows:
                payment=a.payment_status
                totals[only_currency]['confirmed']+=a.amount_minor if payment=='confirmed' else 0
                totals[only_currency]['reported']+=a.amount_minor if payment in ('reported','confirmed') else 0
                if a.user_id!=a.paid_by_user_id:
                    due=a.amount_minor if payment!='confirmed' else 0
                    obligations.append({'payer_id':a.user_id,'payee_id':a.paid_by_user_id,'currency':only_currency,'cents':due})
            completed.append(all(a.payment_status=='confirmed' or a.user_id==a.paid_by_user_id for a in allocated_rows))
        elif not included:completed.append(False)
        receipt_display_state = 'linked' if included else project_share_state(allocated_rows)
        items.append({'kind':'receipt','source_id':case.id,'case_id':case.id,
            'bill_state':receipt_display_state,'allocation_complete':bool(allocated_rows) or included,
            'payment_confirmed':receipt_display_state=='confirmed',
            'merchant':labels.get(case.id,'Receipt #'+str(case.id)),
            'allocations':[{'user_id':a.user_id,'name':users[a.user_id].name if a.user_id in users else 'Member','amount':a.amount_minor/100,'currency':next(iter(currencies),'RON'),'payment_status':a.payment_status} for a in allocated_rows],
            'allocated':bool(allocated_rows),'paid_by_user_id':allocated_rows[0].paid_by_user_id if allocated_rows else case.user_id,
            'currency':next(iter(currencies), 'RON') if len(currencies)==1 else 'MULTI',
            'total':sum(currencies.values())/100 if len(currencies)==1 else None,
            'totals_by_currency':{key:value/100 for key,value in currencies.items()},
            'also_linked_as_split':included,'status':case.status,
            'added_by_user_id':link.added_by_user_id,'readable_by_me':caller_id==case.user_id})
    for expense in db.query(ProjectManualBill).filter_by(project_id=project.id).order_by(ProjectManualBill.created_at,ProjectManualBill.id).all():
        c=currency_code(expense.currency)
        shares=db.query(ProjectExpenseShare).filter_by(project_id=project.id,kind='manual',source_id=expense.id).all()
        if sum(a.amount_minor for a in shares)!=expense.amount_minor:raise ValueError('Incomplete manual project allocation.')
        totals[c]['bill_total']+=expense.amount_minor
        totals[c]['allocated']+=expense.amount_minor
        totals[c]['reported']+=sum(a.amount_minor for a in shares if a.payment_status in ('reported','confirmed'))
        totals[c]['confirmed']+=sum(a.amount_minor for a in shares if a.payment_status=='confirmed')
        completed.append(all(a.payment_status=='confirmed' or a.user_id==a.paid_by_user_id for a in shares))
        for a in shares:
            if a.user_id!=a.paid_by_user_id and a.payment_status!='confirmed':
                obligations.append({'payer_id':a.user_id,'payee_id':a.paid_by_user_id,'currency':c,'cents':a.amount_minor})
        manual_display_state=project_share_state(shares)
        items.append({'kind':'manual','source_id':expense.id,'merchant':expense.merchant,
            'bill_state':manual_display_state,'allocation_complete':manual_display_state!='unallocated',
            'payment_confirmed':manual_display_state=='confirmed',
            'case_id':None,'currency':c,'total':expense.amount_minor/100,
            'status':'settled' if completed[-1] else 'open','added_by_user_id':expense.created_by_user_id,
            'paid_by_user_id':expense.paid_by_user_id,
            'allocations':[{'user_id':a.user_id,'name':users[a.user_id].name if a.user_id in users else 'Member','amount':a.amount_minor/100,'currency':c,'payment_status':a.payment_status} for a in shares]})
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
    due_by_currency=defaultdict(int)
    for obligation in obligations:due_by_currency[obligation['currency']]+=obligation['cents']
    joined_ids={m.user_id for m in members if m.status in ('owner','joined')}
    options = db.get(ProjectOptions,project.id)
    smart_settle = options.smart_settle if options else True
    netting = settlement_plan(obligations, joined_ids,
                {uid:(u.name or 'Member') for uid,u in users.items()})
    if not smart_settle:
        by_pair=defaultdict(int)
        for d in obligations:
            if d['payer_id'] in joined_ids and d['payee_id'] in joined_ids and d['cents']>0:
                by_pair[(d['payer_id'],d['payee_id'],d['currency'])]+=d['cents']
        netting['suggested_settlements']=[{'from_user_id':payer,'from_name':users[payer].name if payer in users else 'Member',
            'to_user_id':payee,'to_name':users[payee].name if payee in users else 'Member',
            'currency':curr,'amount_minor':cents,'amount':cents/100} for (payer,payee,curr),cents in sorted(by_pair.items())]
    # v7.1.48: authoritative source-bill ledger for every joined Project member.
    # Do not derive payment confirmation from Smart settle proposals.
    ledger = {}
    for m in member_rows:
        if m['status'] not in ('owner','joined'): continue
        ledger[m['user_id']] = {'user_id':m['user_id'], 'name':m['name'],
                                'currencies':defaultdict(lambda:{'allocated':0,'reported':0,'confirmed':0,'outstanding':0,'unreported':0}),
                                'bills':[], 'can_remind':False}
    for item in items:
        if item.get('also_linked_as_split'): continue  # same source cannot be billed twice
        currency = item.get('currency')
        payer_id = item.get('paid_by_user_id')
        if currency == 'MULTI': continue  # never invent an FX sum
        for allocation in item.get('allocations', []):
            uid = allocation.get('user_id')
            if uid not in ledger: continue
            minor = amount_minor(allocation.get('amount'))
            status = (allocation.get('payment_status') or 'unpaid').lower()
            self_funded = uid == payer_id
            confirmed = minor if self_funded or status in ('received','confirmed') else 0
            reported = minor if self_funded or status in ('paid','reported','received','confirmed') else 0
            remains = max(0, minor - confirmed)
            unreported = remains if not reported else 0
            currency_for_share = currency_code(allocation.get('currency') or currency)
            figures = ledger[uid]['currencies'][currency_for_share]
            for key,amount in (('allocated',minor),('reported',reported),('confirmed',confirmed),('outstanding',remains),('unreported',unreported)):
                figures[key] += amount
            ledger[uid]['bills'].append({'kind':item['kind'],'source_id':item['source_id'],
                'merchant':item.get('merchant') or 'Receipt','currency':currency_for_share,
                'allocated':minor/100,'reported':reported/100,'confirmed':confirmed/100,
                'outstanding':remains/100,'payment_status':'confirmed' if confirmed else ('reported' if reported else 'unpaid'),
                'paid_by_user_id':payer_id, 'is_self_funded':self_funded})
            if not self_funded and unreported>0: ledger[uid]['can_remind'] = True
    participant_balances=[]
    for row in ledger.values():
        row['currencies']={c:{k:round(v/100,2) for k,v in amounts.items()}
                           for c,amounts in sorted(row['currencies'].items())}
        participant_balances.append(row)
    participant_balances.sort(key=lambda m:(m['name'].casefold(),m['user_id']))
    return {'id':project.id,'name':project.name,
         'smart_settle':smart_settle,'primary_currency':options.primary_currency if options else 'RON',
         'cover_key':cover_of(db,project.id),
         'project_settled':bool(completed) and all(completed),
         'outstanding_by_currency':{c:round(v/100,2) for c,v in due_by_currency.items()},
         'settlement_rule':'Group is settled only when every source Split Bill and project allocation is confirmed.','owner_user_id':project.owner_user_id,
         'is_owner':caller_id==project.owner_user_id,'members':member_rows,
         'participant_balances':participant_balances,
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
              'membership_status':m.status,'cover_key':cover_of(db,p.id),
              'created_at':p.created_at.isoformat()} for p,m in rows]}

@router.get('/candidates')
def candidates(identity=Depends(current),db=Depends(get_db)):
    enabled(); uid=identity[0].id
    cases=(db.query(Case).filter_by(user_id=uid).order_by(Case.created_at.desc()).limit(150).all())
    sessions=(db.query(SplitBillSession).filter_by(owner_user_id=uid)
              .order_by(SplitBillSession.created_at.desc()).limit(150).all())
    case_ids={c.id for c in cases} | {s.case_id for s in sessions}
    amounts=defaultdict(lambda:defaultdict(int))
    labels = {}
    if case_ids:
        for line in db.query(ReceiptItem).filter(ReceiptItem.case_id.in_(case_ids)).all():
            amounts[line.case_id][currency_code(line.currency)]+=amount_minor(line.total_price)
        labels=receipt_labels_safe(db,case_ids)
    return {'items':(
       [{'kind':'receipt','source_id':c.id,'label':labels.get(c.id,f'Receipt #{c.id}')+' · receipt #'+str(c.id),
         'case_id':c.id,'date':c.created_at.isoformat() if c.created_at else '',
         'totals':{k:v/100 for k,v in amounts[c.id].items()}} for c in cases] +
       [{'kind':'split','source_id':s.id,'label':labels.get(s.case_id,f'Receipt #{s.case_id}')+' · split #'+str(s.id),
         'case_id':s.case_id,'date':s.created_at.isoformat() if s.created_at else '',
         'currency':s.currency or 'RON','status':s.status,
         'total':get_split_bill_session_summary(db,s,ensure_translations=False)['grand_total']} for s in sessions])}

@router.post('')
def create_project(body:dict,identity=Depends(current),db=Depends(get_db)):
    enabled();name=body.get('name')
    if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Project name must contain 1–100 characters.')
    project=BillProject(owner_user_id=identity[0].id,name=name.strip())
    db.add(project);db.flush()
    currency=currency_code(body.get('primary_currency') or 'RON')
    db.add(ProjectOptions(project_id=project.id,smart_settle=body.get('smart_settle') is not False,primary_currency=currency))
    db.add(BillProjectMember(project_id=project.id,user_id=identity[0].id,status='owner',joined_at=datetime.utcnow()))
    if body.get('cover_key'):
        db.add(ProjectCoverV7144(project_id=project.id,cover_key=checked_cover(body['cover_key'])))
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
    if db.query(ProjectExpenseShare).filter(ProjectExpenseShare.project_id==project_id,
          ProjectExpenseShare.payment_status=='confirmed',
          ProjectExpenseShare.user_id!=ProjectExpenseShare.paid_by_user_id).first():
        raise HTTPException(409,'This project has confirmed payments and must be retained for audit.')
    db.query(ProjectChatMessage).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(ProjectExpenseShare).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(ProjectManualBill).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(ProjectCoverV7144).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(ProjectOptions).filter_by(project_id=project_id).delete(synchronize_session=False)
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
        if kind=='split':
            matching=next((session for session in sessions if session.id==sid),None)
            if matching:
                old=db.query(ProjectExpenseShare).filter_by(project_id=project_id,kind='receipt',source_id=matching.case_id).all()
                if any(a.payment_status=='confirmed' and a.user_id!=a.paid_by_user_id for a in old):
                    raise HTTPException(409,'Cannot replace a receipt with a Split Bill after Project payments were confirmed.')
                if old:db.query(ProjectExpenseShare).filter_by(project_id=project_id,kind='receipt',source_id=matching.case_id).delete(synchronize_session=False)
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
    if kind not in ('receipt','split','manual'): raise ValueError('Unknown project item type.')
    if kind=='manual':
        expense=db.query(ProjectManualBill).filter_by(id=source_id,project_id=project_id).first()
        if not expense:raise HTTPException(404,'Manual expense not found.')
        if identity[0].id not in (expense.created_by_user_id,project.owner_user_id):
            raise HTTPException(403,'Only the contributor or owner may remove the expense.')
        saved=db.query(ProjectExpenseShare).filter_by(project_id=project_id,kind='manual',source_id=source_id).all()
        if any(a.payment_status=='confirmed' and a.user_id!=a.paid_by_user_id for a in saved):
            raise HTTPException(409,'A confirmed expense cannot be removed from the payment history.')
        db.query(ProjectExpenseShare).filter_by(project_id=project_id,kind='manual',source_id=source_id).delete(synchronize_session=False)
        db.delete(expense);db.commit();return {'removed':True,'original_record_unchanged':True}
    row=db.query(BillProjectItem).filter_by(project_id=project_id,kind=kind,source_id=source_id).first()
    if row and row.added_by_user_id not in (identity[0].id,) and project.owner_user_id!=identity[0].id:
        raise HTTPException(403,'Only the contributor or project owner can remove this entry.')
    changed=0
    if row:
        saved=db.query(ProjectExpenseShare).filter_by(project_id=project_id,kind=kind,source_id=source_id).all()
        if any(a.payment_status=='confirmed' and a.user_id!=a.paid_by_user_id for a in saved):
            raise HTTPException(409,'A confirmed expense cannot be removed from the payment history.')
        db.query(ProjectExpenseShare).filter_by(project_id=project_id,kind=kind,source_id=source_id).delete(synchronize_session=False)
        db.delete(row);changed=1
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
    db.query(ProjectExpenseShare).filter_by(project_id=project.id,user_id=member_user_id).delete(synchronize_session=False)
    db.query(ProjectChatMessage).filter_by(project_id=project.id,user_id=member_user_id).delete(synchronize_session=False)
    db.delete(target);db.commit();return {'revoked':True,'contributed_links_removed':removed}

@router.post('/{project_id}/leave')
def leave_project(project_id:int,identity=Depends(current),db=Depends(get_db)):
    project,member=membership(db,identity[0].id,project_id)
    if project.owner_user_id==identity[0].id:
        raise HTTPException(403,'Transfer or delete a project you own instead.')
    removed=db.query(BillProjectItem).filter_by(project_id=project.id,added_by_user_id=identity[0].id).delete(synchronize_session=False)
    db.query(ProjectExpenseShare).filter_by(project_id=project.id,user_id=identity[0].id).delete(synchronize_session=False)
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


# v7.1.43 project expense/chat extensions. Each method checks accepted membership.

def _accepted_people(db,project_id):
    return {m.user_id for m in db.query(BillProjectMember).filter(
        BillProjectMember.project_id==project_id,
        BillProjectMember.status.in_(('joined','owner'))).all()}


def _verify_share_people(db,pid,mode,values,total,payer):
    if not isinstance(values,list):raise ValueError('Choose the people sharing the expense.')
    accepted=_accepted_people(db,pid)
    if payer not in accepted:raise HTTPException(403,'Payer must belong to the project.')
    result=allocate_minor(total,mode,values)
    if not set(result).issubset(accepted):raise HTTPException(403,'Invite and accept every selected participant first.')
    if not result:raise ValueError('At least one participant required.')
    return result


@router.put('/{project_id}/options')
def update_project_options(project_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    owner(db,identity[0].id,project_id)
    options=db.get(ProjectOptions,project_id)
    if not options:
        options=ProjectOptions(project_id=project_id)
        db.add(options)
    if 'smart_settle' in body:
        if type(body['smart_settle']) is not bool:raise ValueError('Smart settle must be enabled or disabled.')
        options.smart_settle=body['smart_settle']
    if 'cover_key' in body:
        key = body['cover_key']
        row = db.get(ProjectCoverV7144, project_id)
        if key is None:
            if row: db.delete(row)
        else:
            key = checked_cover(key)
            if row: row.cover_key = key
            else: db.add(ProjectCoverV7144(project_id=project_id,cover_key=key))
    db.commit()
    answer={'smart_settle':options.smart_settle}
    if 'cover_key' in body: answer['cover_key']=cover_of(db,project_id)
    return answer


@router.post('/{project_id}/manual')
def add_manual_bill(project_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    membership(db,identity[0].id,project_id)
    uid=identity[0].id
    title=body.get('merchant')
    if not isinstance(title,str) or not 1<=len(title.strip())<=150:raise ValueError('Enter a merchant or description (1–150 characters).')
    cents=to_minor(body.get('amount'))
    if cents<=0:raise ValueError('Amount must be positive.')
    currency=currency_code(body.get('currency'))
    # The authenticated user asserts having paid. Prevent claiming another member paid.
    if body.get('paid_by_user_id',uid)!=uid:raise HTTPException(403,'You can only add expenses you paid.')
    mode=body.get('mode','equal')
    shares=_verify_share_people(db,project_id,mode,body.get('participants'),cents,uid)
    if db.query(ProjectManualBill).filter_by(project_id=project_id).count()>=300:
        raise ValueError('Maximum 300 manual bills per project.')
    expense=ProjectManualBill(project_id=project_id,created_by_user_id=uid,paid_by_user_id=uid,
                              merchant=title.strip(),amount_minor=cents,currency=currency)
    db.add(expense);db.flush()
    for person,amount in shares.items():
        db.add(ProjectExpenseShare(project_id=project_id,kind='manual',source_id=expense.id,
            user_id=person,paid_by_user_id=uid,amount_minor=amount,
            payment_status='confirmed' if person==uid else 'unpaid'))
    db.commit();return {'id':expense.id,'amount':cents/100,'currency':currency,'original_splits_unchanged':True}


@router.put('/{project_id}/receipts/{case_id}/allocate')
def allocate_imported_receipt(project_id:int,case_id:int,body:dict,identity=Depends(current),db=Depends(get_db)):
    membership(db,identity[0].id,project_id)
    link=db.query(BillProjectItem).filter_by(project_id=project_id,kind='receipt',source_id=case_id).with_for_update().first()
    if not link:raise HTTPException(404,'Receipt not in this project.')
    if link.added_by_user_id!=identity[0].id:raise HTTPException(403,'Only the receipt contributor can allocate it.')
    if db.query(ProjectExpenseShare.id).filter_by(project_id=project_id,kind='receipt',source_id=case_id).first():
        raise HTTPException(409,'Receipt is already allocated. Review its participant balances or payment status instead.')
    if db.query(BillProjectItem).filter_by(project_id=project_id,kind='split').join(
        SplitBillSession,SplitBillSession.id==BillProjectItem.source_id).filter(
        SplitBillSession.case_id==case_id).first():
        raise HTTPException(409,'Edit allocations on the existing Split Bill instead.')
    case=db.get(Case,case_id)
    if not case or case.user_id!=identity[0].id:raise HTTPException(404,'Receipt ownership not verified.')
    lines=db.query(ReceiptItem).filter_by(case_id=case_id).all()
    currencies={currency_code(line.currency) for line in lines}
    if len(currencies)!=1:raise ValueError('Choose a single receipt currency before allocating.')
    total=sum(amount_minor(line.total_price) for line in lines)
    if total<=0:raise ValueError('Receipt has no positive amount.')
    result=_verify_share_people(db,project_id,body.get('mode','equal'),body.get('participants'),total,identity[0].id)
    for person,amount in result.items():
        db.add(ProjectExpenseShare(project_id=project_id,kind='receipt',source_id=case_id,
            user_id=person,paid_by_user_id=identity[0].id,amount_minor=amount,
            payment_status='confirmed' if person==identity[0].id else 'unpaid'))
    db.commit();return {'allocated':True,'total':total/100,'currency':next(iter(currencies))}


@router.post('/{project_id}/settlements/{kind}/{source_id}/{share_user_id}/{action}')
def settle_project_share(project_id:int,kind:str,source_id:int,share_user_id:int,action:str,
                         identity=Depends(current),db=Depends(get_db)):
    membership(db,identity[0].id,project_id)
    if kind not in ('receipt','manual') or action not in ('report','confirm'):
        raise HTTPException(404,'Unknown project settlement action.')
    share=db.query(ProjectExpenseShare).filter_by(project_id=project_id,kind=kind,source_id=source_id,
        user_id=share_user_id).with_for_update().first()
    if share is None:raise HTTPException(404,'Allocation not found.')
    if action=='report':
        if identity[0].id!=share_user_id:raise HTTPException(403,'Only the payer can report payment.')
        if share.payment_status!='unpaid':raise HTTPException(409,'Payment was already reported or confirmed.')
        share.payment_status='reported';share.reported_at=datetime.utcnow()
    else:
        if identity[0].id!=share.paid_by_user_id:raise HTTPException(403,'Only the recipient can confirm payment.')
        if share.payment_status!='reported':raise HTTPException(409,'Payer must report payment first.')
        share.payment_status='confirmed';share.confirmed_at=datetime.utcnow()
    db.commit();return {'status':share.payment_status,'source_bill_not_modified':True}



@router.post('/{project_id}/reminders/{participant_id}')
def remind_project_participant(project_id:int,participant_id:int,identity=Depends(current),db=Depends(get_db)):
    """Project-owner reminder. Payer is shown settlement details only after signed-in membership check.

    The original split payment status is authoritative. No payment is marked complete here.
    """
    from app.models.push_notification import PushEvent
    from app.services.push_service import enqueue
    project = owner(db, identity[0].id, project_id)
    if participant_id == identity[0].id:
        raise HTTPException(400,'You cannot remind yourself.')
    member = db.query(BillProjectMember).filter_by(project_id=project_id,user_id=participant_id,status='joined').first()
    if not member: raise HTTPException(404,'The participant must accept the Project invitation first.')
    person = db.get(User,participant_id)
    if not person or person.status != 'active':
        raise HTTPException(404,'The participant account is not active.')
    summary = _project_summary(db, project, identity[0].id)
    row = next((p for p in summary['participant_balances'] if p['user_id']==participant_id), None)
    if not row or not row['can_remind']:
        raise HTTPException(409,'This participant has no outstanding Project payments.')
    pending = [(c,v['unreported']) for c,v in row['currencies'].items() if v['unreported']>0.004]
    if not pending: raise HTTPException(409,'There is no balance to remind about.')
    local_path = f'/projects/{project_id}?view=settlement'
    now = datetime.utcnow()
    # Serialized at the project row in PostgreSQL to guard duplicate submissions.
    db.query(BillProject).filter_by(id=project_id).with_for_update().first()
    recent = (db.query(PushEvent).filter(PushEvent.user_id==participant_id,
                   PushEvent.kind=='project_reminder',PushEvent.url==local_path,
                   PushEvent.created_at>now-timedelta(hours=1))
              .order_by(PushEvent.created_at.desc()).first())
    if recent: raise HTTPException(429,'A Project reminder was already sent to this participant recently.')
    amounts=', '.join(f'{value:.2f} {currency}' for currency,value in pending)
    is_ro=person.preferred_language=='ro'
    title=(f'Memento plată · {project.name}' if is_ro else f'Project payment reminder · {project.name}')
    body=(f'Ai de achitat {amounts}. Deschide proiectul pentru detaliile de plată oferite de destinatar.' if is_ro else
          f'Your outstanding Project amount: {amounts}. Open the Project to see payment options shared by the recipient.')
    # Never put an IBAN, external payment URL or invite token into a push/email.
    event = enqueue(db,participant_id,'project_reminder',title,body,local_path)
    db.commit()
    return {'queued':True,'event_id':event.id,'target':local_path,'outstanding':[
        {'currency':c,'amount':v} for c,v in pending]}

@router.get('/{project_id}/chat')
def project_chat(project_id:int,identity=Depends(current),db=Depends(get_db)):
    membership(db,identity[0].id,project_id)
    messages=(db.query(ProjectChatMessage).filter_by(project_id=project_id)
      .order_by(ProjectChatMessage.id.desc()).limit(80).all())
    user_ids={m.user_id for m in messages}
    names={u.id:u.name for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return {'messages':[{'id':m.id,'user_id':m.user_id,'sender':names.get(m.user_id,'Member'),
             'text':m.body,'created_at':m.created_at.isoformat()} for m in reversed(messages)]}


@router.post('/{project_id}/chat')
def send_project_chat(project_id:int,body:dict,request:Request,identity=Depends(current),db=Depends(get_db)):
    membership(db,identity[0].id,project_id)
    limit(db,request,'project-chat',30)
    content=body.get('text')
    if not isinstance(content,str) or not 1<=len(content.strip())<=1200:
        raise ValueError('Message must contain 1–1200 characters.')
    recent=db.query(ProjectChatMessage).filter_by(project_id=project_id,user_id=identity[0].id).order_by(
         ProjectChatMessage.id.desc()).first()
    if recent and (datetime.utcnow()-recent.created_at).total_seconds()<2:
        raise HTTPException(429,'Please slow down before posting again.')
    m=ProjectChatMessage(project_id=project_id,user_id=identity[0].id,body=content.strip())
    db.add(m);db.commit();return {'id':m.id,'sent':True}
