"""Atomic, merchant-reviewed loyalty receipt packages.

Every receipt needs its own customer-issued verification code and consented
image review. A package approval credits the complete remaining set together;
it never asserts that bank or POS settlement was independently verified.
"""
from datetime import timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Merchant, Membership, Program, ReceiptClaim, Reward, Store, Staff, utcnow
from .models_v06 import ReceiptEvidenceAccess
from .models_v12 import CustomerClaimCode
from .pilot_readiness_v069 import require_reward_schema
from .pilot_v05 import aware
from .pilot_v06 import approval_guard
from .receipt_claim_access_v0610 import code_is_unlocked
from .security import merchant_actor

router = APIRouter(tags=['Loyalty receipt packages'])


class PackageApproval(BaseModel):
    program_id: str = Field(min_length=36, max_length=36)
    consumer_id: str = Field(min_length=20, max_length=100)
    claim_ids: list[str] = Field(min_length=1, max_length=30)


def _manager(staff):
    if staff.role not in ('owner', 'manager'):
        raise HTTPException(403, 'Merchant manager role required')


def _reviewed(db, claim, staff, code, now):
    """Both code unlock and actual evidence review are required for EACH item."""
    if not code or not code_is_unlocked(code, staff.id, now=now):
        return False
    review = db.scalar(
        select(ReceiptEvidenceAccess)
        .where(ReceiptEvidenceAccess.claim_id == claim.id,
               ReceiptEvidenceAccess.merchant_id == staff.merchant_id,
               ReceiptEvidenceAccess.staff_id == staff.id,
               ReceiptEvidenceAccess.action == 'view')
        .order_by(ReceiptEvidenceAccess.at.desc())
        .limit(1)
    )
    return bool(review and aware(now) - timedelta(minutes=15) <= aware(review.at) <= aware(now)
                and aware(review.at) >= aware(code.unlocked_at))


@router.get('/v1/merchant/claims/packages')
def receipt_packages(staff: Staff = Depends(merchant_actor), db: Session = Depends(get_db)):
    _manager(staff)
    from sqlalchemy import inspect
    if not inspect(db.get_bind()).has_table(CustomerClaimCode.__tablename__):
        return []
    # Limit the review inbox and never expose images or plaintext QR codes.
    claims = db.scalars(
        select(ReceiptClaim)
        .where(ReceiptClaim.merchant_id == staff.merchant_id, ReceiptClaim.status == 'pending')
        .order_by(ReceiptClaim.created_at)
        .limit(200)
    ).all()
    if not claims:
        return []
    codes = {code.claim_id: code for code in db.scalars(
        select(CustomerClaimCode).where(
            CustomerClaimCode.merchant_id == staff.merchant_id,
            CustomerClaimCode.claim_id.in_([c.id for c in claims])
        )
    ).all()}
    groups = defaultdict(list)
    for claim in claims:
        if claim.id in codes:
            groups[(claim.program_id, claim.consumer_id)].append(claim)
    now = utcnow()
    result = []
    for (program_id, consumer_id), rows in groups.items():
        program = db.get(Program, program_id)
        if not program or program.merchant_id != staff.merchant_id:
            continue
        member = db.scalar(select(Membership).where(
            Membership.program_id == program_id,
            Membership.consumer_id == consumer_id
        ))
        needed = max(0, program.stamps_required - (member.stamps if member else 0))
        items = [
            {'claim_id': c.id, 'amount_minor': c.amount_minor,
             'submitted_at': c.created_at.isoformat(),
             'reviewed': _reviewed(db, c, staff, codes.get(c.id), now)}
            for c in rows
        ]
        complete = bool(member and needed > 0 and len(items) == needed and
                        all(item['reviewed'] for item in items))
        result.append({
            'program_id': program_id, 'program_title': program.title,
            'consumer_id': consumer_id,
            'consumer_label': consumer_id[:10],
            'required': program.stamps_required,
            'already_verified': member.stamps if member else 0,
            'remaining': needed,
            'pending_count': len(items), 'items': items,
            'ready_to_approve': complete,
            'message': ('Ready for one atomic package approval' if complete else
                        'Each required receipt needs its own QR unlock and review; no partial stamps are credited'),
        })
    return result


@router.post('/v1/merchant/claims/packages/approve')
def approve_receipt_package(payload: PackageApproval,
                            staff: Staff = Depends(merchant_actor),
                            db: Session = Depends(get_db)):
    _manager(staff)
    require_reward_schema(db)
    program = db.get(Program, payload.program_id)
    if not program or program.merchant_id != staff.merchant_id:
        raise HTTPException(404, 'Loyalty program not found')
    if program.status not in ('published', 'paused'):
        raise HTTPException(409, 'This loyalty program is not eligible for review')
    merchant = db.get(Merchant, staff.merchant_id)
    store = db.get(Store, program.store_id)
    if not merchant or merchant.status != 'active' or not store or not store.active:
        raise HTTPException(409, 'Merchant or store is unavailable')
    membership = db.scalar(
        select(Membership).where(
            Membership.program_id == program.id,
            Membership.consumer_id == payload.consumer_id
        ).with_for_update()
    )
    if not membership:
        raise HTTPException(409, 'Customer has left this program; receipt package cannot be approved')
    needed = program.stamps_required - membership.stamps
    if needed < 1 or needed > 30:
        raise HTTPException(409, 'Loyalty package criteria cannot be completed')
    ids = payload.claim_ids
    if len(ids) != needed or len(set(ids)) != len(ids):
        raise HTTPException(409, f'Exactly {needed} distinct pending receipts are required')
    pending = db.scalars(
        select(ReceiptClaim)
        .where(ReceiptClaim.merchant_id == staff.merchant_id,
               ReceiptClaim.program_id == program.id,
               ReceiptClaim.consumer_id == payload.consumer_id,
               ReceiptClaim.status == 'pending')
        .with_for_update()
    ).all()
    # Reject stale selections and overfilled packages instead of silently
    # awarding some receipts and leaving other submitted receipts behind.
    if {c.id for c in pending} != set(ids):
        raise HTTPException(409, 'Receipt package has changed; refresh before approving')
    codes = {code.claim_id: code for code in db.scalars(
        select(CustomerClaimCode).where(
            CustomerClaimCode.merchant_id == staff.merchant_id,
            CustomerClaimCode.claim_id.in_(ids)
        )
    ).all()}
    for claim in pending:
        if claim.id not in codes:
            raise HTTPException(409, 'Every receipt needs its own customer-issued verification QR')
        if claim.amount_minor < program.min_purchase_minor:
            raise HTTPException(409, 'Receipt does not meet minimum purchase criteria')
        # Existing v0.6 guard checks consent, image review within 15 minutes,
        # staff-specific QR unlock and expiry. Failure rolls back ALL decisions.
        approval_guard(db, claim, staff)
    for claim in pending:
        claim.status = 'approved'
    membership.stamps += len(pending)
    awarded = False
    if membership.stamps >= program.stamps_required:
        membership.stamps -= program.stamps_required
        db.add(Reward(
            merchant_id=staff.merchant_id, program_id=program.id,
            consumer_id=payload.consumer_id, source_claim_id=pending[-1].id
        ))
        awarded = True
    db.commit()
    return {'status': 'approved', 'approved_receipts': len(pending),
            'reward_awarded': awarded, 'stamps': membership.stamps,
            'message': 'Merchant confirmed the complete receipt package; not independent payment confirmation'}
