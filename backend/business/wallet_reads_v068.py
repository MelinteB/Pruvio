"""Backward-compatible, read-only loyalty snapshots.

Selecting explicit legacy columns lets users view existing memberships and rewards
while additive discount reconciliation migrations are pending. Does not create,
approve, reserve, or redeem anything and does not bypass schema readiness.
"""
from sqlalchemy import select
from .models import Membership, Program, Reward

def membership_rows(db, consumer_id: str):
    rows = db.execute(
        select(Membership.program_id, Membership.stamps,
               Program.title, Program.stamps_required, Program.status)
        .select_from(Membership)
        .outerjoin(Program, Membership.program_id == Program.id)
        .where(Membership.consumer_id == consumer_id)
        .order_by(Membership.id)
    ).all()
    return [{
        'program_id': row.program_id, 'stamps': row.stamps,
        'title': row.title or 'Loyalty program',
        'stamps_required': row.stamps_required or 0,
        'status': row.status or 'unavailable',
    } for row in rows]

def reward_rows(db, consumer_id: str):
    # Do NOT load the full Reward ORM entity here. Source claim tracking was
    # added in b10, so SELECT * would break pre-migration customer wallets.
    rows = db.execute(
        select(Reward.id, Reward.program_id, Reward.status,
               Reward.redemption_code, Reward.reserved_until)
        .where(Reward.consumer_id == consumer_id)
        .order_by(Reward.id)
    ).all()
    return [{
        'id': row.id,
        'program_id': row.program_id,
        'status': row.status,
        'code': row.redemption_code if row.status == 'reserved' else None,
        'reserved_until': row.reserved_until.isoformat() if row.reserved_until else None,
    } for row in rows]
