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
