"""Pruvs Business v0.6.12: DB-managed pilot access without syncing identity tables.

Business remains authority for merchant IDs and enrollment. Core consumes
read-only eligibility via the existing Business API. Only a separately provisioned
platform_admin account can approve/revoke, never a merchant owner or Core.
"""
from __future__ import annotations

import os
from datetime import timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Merchant, Program, Staff, Store, utcnow
from .models_v0612 import MerchantPilotEnrollment, MerchantPilotAudit
from .models_v0726 import ProgramPilotEnrollment, ProgramPilotAudit
from .security import merchant_actor

router = APIRouter(tags=['Loyalty pilot enrollment'])
DB_FLAG = 'PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED'


def db_mode_enabled():
    return os.getenv(DB_FLAG, 'false').strip().lower() == 'true'


def tables_ready(db):
    """Read-only schema check, avoids query failure poisoning a PG transaction."""
    try:
        inspector = inspect(db.get_bind())
        return (inspector.has_table(MerchantPilotEnrollment.__tablename__)
                and inspector.has_table(MerchantPilotAudit.__tablename__))
    except Exception:
        return False


def require_db_mode(db):
    if not db_mode_enabled():
        raise HTTPException(503, 'Database-managed pilot enrollment is disabled.')
    if not tables_ready(db):
        raise HTTPException(503, 'Merchant pilot migration b11 is not ready.')


def legacy_allowed(merchant_id):
    return merchant_id in {
        item.strip() for item in os.getenv(
            'PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS', '').split(',')
        if item.strip()
    }


def merchant_pilot_allowed(db, merchant_id):
    """Fail closed when in DB mode; legacy allowlist is opt-in rollback only."""
    if not merchant_id:
        return False
    if not db_mode_enabled():
        return legacy_allowed(merchant_id)
    if not tables_ready(db):
        return False
    merchant = db.get(Merchant, merchant_id)
    if not merchant or merchant.status != 'active':
        return False
    access = db.get(MerchantPilotEnrollment, merchant_id)
    return bool(access is not None and access.status == 'approved')


def program_scope_tables_ready(db):
    try:
        inspector = inspect(db.get_bind())
        return (inspector.has_table(ProgramPilotEnrollment.__tablename__)
                and inspector.has_table(ProgramPilotAudit.__tablename__))
    except Exception:
        return False


def program_pilot_allowed(db, program):
    """Approval must match the exact program, merchant, and current store."""
    if not program:
        return False
    if not db_mode_enabled():
        return legacy_allowed(program.merchant_id)
    if not program_scope_tables_ready(db):
        return False
    merchant = db.get(Merchant, program.merchant_id)
    store = db.get(Store, program.store_id)
    if (not merchant or merchant.status != 'active' or not store or not store.active
            or store.merchant_id != program.merchant_id or program.status != 'published'):
        return False
    row = db.get(ProgramPilotEnrollment, program.id)
    return bool(row and row.status == 'approved'
                and row.merchant_id == program.merchant_id
                and row.store_id == program.store_id)


def program_enrollment_json(row, *, program=None, store=None, merchant=None):
    return {
        'program_id': row.program_id if row else (program.id if program else None),
        'merchant_id': row.merchant_id if row else (program.merchant_id if program else None),
        'store_id': row.store_id if row else (program.store_id if program else None),
        'program_title': program.title if program else 'Unknown program',
        'store_name': store.name if store else 'Unknown location',
        'merchant_name': merchant.name if merchant else 'Unknown merchant',
        'status': row.status if row else 'not_requested',
        'requested_at': row.requested_at.isoformat() if row else None,
        'reviewed_at': row.reviewed_at.isoformat() if row and row.reviewed_at else None,
        'allowed': bool(row and row.status == 'approved'
                        and program and program.status == 'published'
                        and store and store.active
                        and merchant and merchant.status == 'active'),
        'program_published': bool(program and program.status == 'published'),
        'location_active': bool(store and store.active),
        'merchant_active': bool(merchant and merchant.status == 'active'),
    }


def add_program_audit(db, row, staff_id, action, old_status, new_status, note=''):
    db.add(ProgramPilotAudit(program_id=row.program_id, merchant_id=row.merchant_id,
        store_id=row.store_id, actor_staff_id=staff_id, action=action,
        old_status=old_status, new_status=new_status, note=note))


def require_platform_admin(staff: Staff = Depends(merchant_actor)):
    # The platform role is granted offline by an authorized DB operator.
    # Merchant registration, merchant owners and Core cannot grant it.
    if staff.role != 'platform_admin' or not staff.active:
        raise HTTPException(403, 'Platform administrator permission required.')
    return staff


def merchant_is_eligible(db, merchant_id):
    merchant = db.get(Merchant, merchant_id)
    if not merchant or merchant.status != 'active':
        return False
    published = db.scalars(select(Program).where(
        Program.merchant_id == merchant_id, Program.status == 'published'
    )).all()
    return any(bool(store and store.active and store.merchant_id == merchant_id)
               for p in published
               for store in [db.get(Store, p.store_id)])


def enrollment_json(row, *, mode):
    return {
        'mode': mode, 'merchant_id': row.merchant_id if row else None,
        'status': row.status if row else 'not_requested',
        'requested_at': row.requested_at.isoformat() if row else None,
        'reviewed_at': row.reviewed_at.isoformat() if row and row.reviewed_at else None,
        'allowed': bool(row and row.status == 'approved'),
    }


def add_audit(db, merchant_id, staff_id, action, old_status, new_status, note=''):
    db.add(MerchantPilotAudit(
        merchant_id=merchant_id, actor_staff_id=staff_id,
        action=action, old_status=old_status, new_status=new_status,
        note=note,
    ))


@router.get('/v1/merchant/pilot-access')
def my_pilot_access(staff: Staff = Depends(merchant_actor),
                    db: Session = Depends(get_db)):
    if not db_mode_enabled():
        allowed = legacy_allowed(staff.merchant_id)
        return {
            'mode': 'legacy', 'merchant_id': staff.merchant_id,
            'status': 'approved' if allowed else 'not_requested',
            'allowed': allowed, 'request_supported': False,
        }
    require_db_mode(db)
    row = db.get(MerchantPilotEnrollment, staff.merchant_id)
    return {**enrollment_json(row, mode='database'),
            'merchant_id': staff.merchant_id,
            'request_supported': staff.role in ('owner','manager'),
            'has_published_program': merchant_is_eligible(db, staff.merchant_id)}


@router.post('/v1/merchant/pilot-access/request')
def request_pilot_access(staff: Staff = Depends(merchant_actor),
                         db: Session = Depends(get_db)):
    require_db_mode(db)
    if staff.role not in ('owner','manager'):
        raise HTTPException(403, 'Merchant owner or manager required.')
    db.scalar(select(Merchant).where(Merchant.id == staff.merchant_id).with_for_update())
    if not merchant_is_eligible(db, staff.merchant_id):
        raise HTTPException(409, 'An active merchant, store and published loyalty program are required.')
    row = db.scalar(select(MerchantPilotEnrollment).where(
        MerchantPilotEnrollment.merchant_id == staff.merchant_id
    ).with_for_update())
    if row is not None and row.status in ('requested','approved'):
        return {**enrollment_json(row, mode='database'), 'request_supported': True}
    now = utcnow()
    previous = row.status if row else 'not_requested'
    if row is None:
        row = MerchantPilotEnrollment(
            merchant_id=staff.merchant_id, status='requested',
            requested_by_staff_id=staff.id, requested_at=now, updated_at=now,
        )
        db.add(row)
    else:
        row.status = 'requested'
        row.requested_by_staff_id = staff.id
        row.requested_at = now
        row.reviewed_by_staff_id = None
        row.reviewed_at = None
        row.updated_at = now
    add_audit(db, staff.merchant_id, staff.id, 'request', previous, 'requested')
    db.commit()
    return {**enrollment_json(row, mode='database'), 'request_supported': True}


class PilotDecisionIn(BaseModel):
    action: Literal['approve','deny','revoke']
    note: str = Field(default='', max_length=300)


def _program_scope_row(db, program_id, *, lock=False):
    query = select(ProgramPilotEnrollment).where(
        ProgramPilotEnrollment.program_id == program_id)
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


@router.get('/v1/merchant/pilot-programs')
def merchant_pilot_programs(staff: Staff = Depends(merchant_actor),
                            db: Session = Depends(get_db)):
    require_db_mode(db)
    if not program_scope_tables_ready(db):
        raise HTTPException(503, 'Program-specific approval migration b17 is not ready.')
    programs = db.scalars(select(Program).where(
        Program.merchant_id == staff.merchant_id).order_by(Program.title)).all()
    result = []
    for program in programs:
        store = db.get(Store, program.store_id)
        merchant = db.get(Merchant, program.merchant_id)
        row = _program_scope_row(db, program.id)
        result.append(program_enrollment_json(row, program=program, store=store, merchant=merchant))
    return {'mode': 'program_scoped', 'request_supported': staff.role in ('owner','manager'),
            'programs': result}


@router.post('/v1/merchant/programs/{program_id}/pilot-access/request')
def request_program_pilot_access(program_id: str, staff: Staff = Depends(merchant_actor),
                                 db: Session = Depends(get_db)):
    require_db_mode(db)
    if not program_scope_tables_ready(db):
        raise HTTPException(503, 'Program-specific approval migration b17 is not ready.')
    if staff.role not in ('owner','manager'):
        raise HTTPException(403, 'Merchant owner or manager required.')
    program = db.scalar(select(Program).where(
        Program.id == program_id, Program.merchant_id == staff.merchant_id).with_for_update())
    if not program:
        raise HTTPException(404, 'Loyalty program not found.')
    store = db.get(Store, program.store_id)
    merchant = db.get(Merchant, program.merchant_id)
    if not merchant or merchant.status != 'active':
        raise HTTPException(409, 'Activate this merchant account before requesting campaign approval.')
    if not store or store.merchant_id != program.merchant_id or not store.active:
        raise HTTPException(409, 'Activate this program’s location before requesting campaign approval.')
    if program.status != 'published':
        raise HTTPException(409, 'Publish this exact loyalty program before requesting campaign approval.')
    row = _program_scope_row(db, program.id, lock=True)
    if row and row.status in ('requested','approved') and row.store_id == program.store_id:
        return program_enrollment_json(row, program=program, store=store, merchant=merchant)
    now = utcnow()
    previous = row.status if row else 'not_requested'
    if row is None:
        row = ProgramPilotEnrollment(program_id=program.id, merchant_id=program.merchant_id,
            store_id=program.store_id, status='requested', requested_by_staff_id=staff.id,
            requested_at=now, updated_at=now)
        db.add(row)
    else:
        row.merchant_id=program.merchant_id;row.store_id=program.store_id
        row.status='requested';row.requested_by_staff_id=staff.id
        row.reviewed_by_staff_id=None;row.reviewed_at=None
        row.requested_at=now;row.updated_at=now
    add_program_audit(db,row,staff.id,'request',previous,'requested')
    db.commit()
    return program_enrollment_json(row, program=program, store=store, merchant=merchant)


@router.get('/v1/platform/pilot-program-enrollments')
def platform_pilot_program_enrollments(staff: Staff = Depends(require_platform_admin),
                                       db: Session = Depends(get_db)):
    require_platform_admin(staff)
    require_db_mode(db)
    if not program_scope_tables_ready(db):
        raise HTTPException(503, 'Program-specific approval migration b17 is not ready.')
    rows=db.scalars(select(ProgramPilotEnrollment).order_by(
        ProgramPilotEnrollment.updated_at.desc()).limit(200)).all()
    result=[]
    for row in rows:
        program=db.get(Program,row.program_id);store=db.get(Store,row.store_id)
        merchant=db.get(Merchant,row.merchant_id)
        result.append(program_enrollment_json(row,program=program,store=store,merchant=merchant))
    return result


@router.post('/v1/platform/pilot-program-enrollments/{program_id}/decision')
def platform_decide_program_pilot(program_id: str, body: PilotDecisionIn,
                                  staff: Staff = Depends(require_platform_admin),
                                  db: Session = Depends(get_db)):
    require_platform_admin(staff)
    require_db_mode(db)
    if not program_scope_tables_ready(db):
        raise HTTPException(503, 'Program-specific approval migration b17 is not ready.')
    row=_program_scope_row(db,program_id,lock=True)
    if not row:
        raise HTTPException(404,'This loyalty program has not requested approval.')
    program=db.get(Program,row.program_id);store=db.get(Store,row.store_id)
    merchant=db.get(Merchant,row.merchant_id)
    if (not program or not store or not merchant or program.merchant_id!=row.merchant_id
            or program.store_id!=row.store_id or store.merchant_id!=row.merchant_id):
        raise HTTPException(409,'The requested program, merchant and location no longer match. Refresh the request.')
    if body.action in ('approve','deny') and row.status!='requested':
        raise HTTPException(409,'Only this program’s pending request can be approved or denied.')
    if body.action=='revoke' and row.status!='approved':
        raise HTTPException(409,'Only this program’s approved receipt rewards can be paused.')
    if body.action=='approve' and (program.status!='published' or not store.active or merchant.status!='active'):
        raise HTTPException(409,'This exact program, location and merchant must all be active before approval.')
    if body.action=='deny' and not body.note.strip():
        raise HTTPException(422,'Provide a reason when denying this program approval.')
    previous=row.status;new_status={'approve':'approved','deny':'denied','revoke':'revoked'}[body.action]
    row.status=new_status;row.reviewed_by_staff_id=staff.id
    row.reviewed_at=utcnow();row.updated_at=row.reviewed_at
    add_program_audit(db,row,staff.id,body.action,previous,new_status,body.note.strip())
    db.commit()
    return program_enrollment_json(row,program=program,store=store,merchant=merchant)


@router.get('/v1/platform/pilot-program-enrollments/{program_id}/history')
def platform_program_pilot_history(program_id: str,
                                   staff: Staff = Depends(require_platform_admin),
                                   db: Session = Depends(get_db)):
    require_platform_admin(staff)
    require_db_mode(db)
    if not program_scope_tables_ready(db):
        raise HTTPException(503, 'Program-specific approval migration b17 is not ready.')
    rows=db.scalars(select(ProgramPilotAudit).where(
        ProgramPilotAudit.program_id==program_id).order_by(
            ProgramPilotAudit.created_at.desc()).limit(100)).all()
    return [{'id':x.id,'program_id':x.program_id,'store_id':x.store_id,
        'action':x.action,'old_status':x.old_status,'new_status':x.new_status,
        'actor_staff_id':x.actor_staff_id,'note':x.note,
        'created_at':x.created_at.isoformat()} for x in rows]


@router.get('/v1/platform/pilot-enrollments')
def platform_pilot_enrollments(staff: Staff = Depends(require_platform_admin),
                               db: Session = Depends(get_db)):
    require_platform_admin(staff)
    require_db_mode(db)
    rows = db.scalars(select(MerchantPilotEnrollment).order_by(
        MerchantPilotEnrollment.updated_at.desc()
    ).limit(100)).all()
    result = []
    for row in rows:
        merchant = db.get(Merchant, row.merchant_id)
        result.append({**enrollment_json(row, mode='database'),
                       'merchant_name': merchant.name if merchant else 'Unknown merchant',
                       'merchant_active': bool(merchant and merchant.status == 'active')})
    return result


@router.post('/v1/platform/pilot-enrollments/{merchant_id}/decision')
def platform_decide_pilot(merchant_id: str, body: PilotDecisionIn,
                          staff: Staff = Depends(require_platform_admin),
                          db: Session = Depends(get_db)):
    require_platform_admin(staff)
    require_db_mode(db)
    row = db.scalar(select(MerchantPilotEnrollment).where(
        MerchantPilotEnrollment.merchant_id == merchant_id
    ).with_for_update())
    if row is None:
        raise HTTPException(404, 'Merchant has not requested pilot access.')
    new_status = {'approve':'approved','deny':'denied','revoke':'revoked'}[body.action]
    if body.action in ('approve','deny') and row.status != 'requested':
        raise HTTPException(409, 'Only pending merchant requests can be approved or denied.')
    if body.action == 'revoke' and row.status != 'approved':
        raise HTTPException(409, 'Only approved merchant access can be revoked.')
    if body.action == 'approve' and not merchant_is_eligible(db, merchant_id):
        raise HTTPException(409, 'Merchant has no active published loyalty program.')
    if body.action == 'deny' and not body.note.strip():
        raise HTTPException(422, 'Provide a reason when denying pilot access.')
    previous = row.status
    row.status = new_status
    row.reviewed_by_staff_id = staff.id
    row.reviewed_at = utcnow()
    row.updated_at = row.reviewed_at
    add_audit(db, merchant_id, staff.id, body.action, previous, new_status, body.note.strip())
    db.commit()
    return {**enrollment_json(row, mode='database'), 'merchant_id': merchant_id}


@router.get('/v1/platform/pilot-enrollments/{merchant_id}/history')
def platform_pilot_history(merchant_id: str,
                           staff: Staff = Depends(require_platform_admin),
                           db: Session = Depends(get_db)):
    require_platform_admin(staff)
    require_db_mode(db)
    events = db.scalars(select(MerchantPilotAudit).where(
        MerchantPilotAudit.merchant_id == merchant_id
    ).order_by(MerchantPilotAudit.created_at.desc()).limit(100)).all()
    return [
        {'id':event.id, 'action':event.action,
         'old_status':event.old_status, 'new_status':event.new_status,
         'actor_staff_id':event.actor_staff_id, 'note':event.note,
         'created_at':event.created_at.isoformat()}
        for event in events
    ]
