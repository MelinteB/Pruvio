"""Atomic quota admission for Pruvs React OCR and expense-report creation.

PostgreSQL advisory transaction locks serialize reservations for a given user.
An independent short-lived session avoids mixing quota accounting with OCR's
existing multi-commit workflow. Charge is refunded on application failure or
image duplicate; no charge is made when a request is denied.
"""
from datetime import datetime, timedelta
import secrets
from fastapi import HTTPException
from sqlalchemy import func, text
from app.db.database import SessionLocal
from app.models.pruvs_usage import PruvsMeteredUse
from app.models.pruvs_commerce import CreditEntry
from app.react_app.plan_catalog import credit_costs

COSTS = {'ocr': 2, 'expense_report': 5}
LIMIT_KEYS = {'ocr': 'ocr_allowance', 'expense_report': 'expense_reports'}


def month_key(now=None):
    return (now or datetime.utcnow()).strftime('%Y-%m')


def lock_user(db, uid):
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace, :uid)'),
                   {'namespace': 791120, 'uid': int(uid)})


def used(db, uid, resource, month=None):
    return int(db.query(func.count(PruvsMeteredUse.id)).filter(
        PruvsMeteredUse.user_id == uid,
        PruvsMeteredUse.resource == resource,
        PruvsMeteredUse.month == (month or month_key()),
        PruvsMeteredUse.state.in_(('reserved', 'completed')),
        PruvsMeteredUse.paid_with == 'allowance',
    ).scalar() or 0)


def metered(db, uid, resource, month=None):
    return int(db.query(func.count(PruvsMeteredUse.id)).filter(
        PruvsMeteredUse.user_id == uid,
        PruvsMeteredUse.resource == resource,
        PruvsMeteredUse.month == (month or month_key()),
        PruvsMeteredUse.state == 'completed',
    ).scalar() or 0)


def credit_balance(db, uid):
    return int(db.query(func.coalesce(func.sum(CreditEntry.delta), 0))
               .filter(CreditEntry.user_id == uid).scalar() or 0)


def bonus_remaining(db, uid):
    from app.models.pruvs_rewards_policy import PruvsOCRBonusGrant
    granted=int(db.query(func.coalesce(func.sum(PruvsOCRBonusGrant.amount),0)).filter_by(user_id=uid).scalar() or 0)
    spent=int(db.query(func.count(PruvsMeteredUse.id)).filter(
        PruvsMeteredUse.user_id==uid,PruvsMeteredUse.resource=='ocr',
        PruvsMeteredUse.paid_with=='bonus',
        PruvsMeteredUse.state.in_(('reserved','completed'))).scalar() or 0)
    return max(0,granted-spent)


def stale_reservations(db, uid):
    """Recover operations abandoned for over 24 hours, preserving refunds."""
    rows = db.query(PruvsMeteredUse).filter(
        PruvsMeteredUse.user_id == uid,
        PruvsMeteredUse.state == 'reserved',
        PruvsMeteredUse.created_at < datetime.utcnow() - timedelta(days=1),
    ).all()
    for row in rows:
        row.state = 'cancelled'
        if row.paid_with == 'credits':
            db.add(CreditEntry(user_id=uid, delta=row.credit_cost,
                               reason='usage_refund', reference='usage-refund:' + row.token))


def reserve(uid, resource, plans, plan, use_credits=False):
    """Reserve one operation before its costly work; return unique reservation token.

    Included units are always used before PC. A user must explicitly opt in to
    spending credits once the included allowance is exhausted.
    """
    if resource not in COSTS:
        raise ValueError('Unsupported billable operation.')
    if plan not in plans:
        raise ValueError('Unknown account subscription.')
    key = LIMIT_KEYS[resource]
    limit = int(plans[plan][key])
    with SessionLocal() as db:
        lock_user(db, uid)
        stale_reservations(db, uid)
        consumed = used(db, uid, resource)
        has_bonus = resource=='ocr' and consumed >= limit and bonus_remaining(db,uid)>0
        charge_credits = consumed >= limit and not has_bonus
        cost = credit_costs(db)[resource]
        balance = credit_balance(db, uid)
        if charge_credits and (not use_credits or balance < cost):
            # Deliberately no quota insert / credit deduction for a denied request.
            db.rollback()
            raise HTTPException(status_code=402, detail={
                'code': 'subscription_limit',
                'message': f'Monthly {resource.replace("_", " ")} allowance reached. Visit Membership to request a different plan or use Pruvs Credits.',
                'resource': resource, 'plan': plan, 'limit': limit,
                'used': consumed, 'credit_cost': cost, 'credits': balance,
                'membership_url': '/account?limit=' + resource + '#membership',
                'purchase_available': False,
            })
        token = secrets.token_urlsafe(24)
        db.add(PruvsMeteredUse(user_id=uid, resource=resource, month=month_key(),
                               state='reserved', token=token,
                               paid_with='credits' if charge_credits else 'bonus' if has_bonus else 'allowance',
                               credit_cost=cost if charge_credits else 0))
        if charge_credits:
            db.add(CreditEntry(user_id=uid, delta=-cost,
                               reason='extra_' + resource,
                               reference='usage-charge:' + token))
        db.commit()
        return token


def finish(token, success):
    """Idempotently confirm or return credits for failed/duplicate operations."""
    with SessionLocal() as db:
        row = db.query(PruvsMeteredUse).filter_by(token=token).first()
        if not row or row.state != 'reserved':
            return
        lock_user(db, row.user_id)
        # Refresh after lock in case another worker has already finished it.
        db.refresh(row)
        if row.state != 'reserved':
            return
        row.state = 'completed' if success else 'cancelled'
        if success:
            row.completed_at = datetime.utcnow()
        elif row.paid_with == 'credits':
            db.add(CreditEntry(user_id=row.user_id, delta=row.credit_cost,
                               reason='usage_refund', reference='usage-refund:' + row.token))
        db.commit()
