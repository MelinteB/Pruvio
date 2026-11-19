"""Keep a loyalty enrollment open only while it holds customer value.

A redeemed voucher completes its earning cycle if there are no remaining
stamps, pending receipt approvals, or other unredeemed vouchers. This does
NOT remove receipt claims, rewards, or the discount reconciliation ledger.

The caller holds the reward row lock and must flush the redeemed status before
checking for other active rewards, because Business uses autoflush=False.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Membership, ReceiptClaim, Reward


def close_completed_cycle(db: Session, *, consumer_id: str, program_id: str) -> bool:
    """Delete only an empty membership; commit remains the caller's responsibility.

    Locking the membership serializes with merchant receipt approvals, which
    also lock the same membership before awarding stamps.
    """
    member = db.scalar(
        select(Membership)
        .where(Membership.consumer_id == consumer_id,
               Membership.program_id == program_id)
        .with_for_update()
    )
    if member is None or member.stamps != 0:
        return False

    pending_claim = db.scalar(
        select(ReceiptClaim.id).where(
            ReceiptClaim.consumer_id == consumer_id,
            ReceiptClaim.program_id == program_id,
            ReceiptClaim.status == 'pending',
        ).limit(1)
    )
    if pending_claim is not None:
        return False

    active_reward = db.scalar(
        select(Reward.id).where(
            Reward.consumer_id == consumer_id,
            Reward.program_id == program_id,
            Reward.status.in_(('available', 'reserved')),
        ).limit(1)
    )
    if active_reward is not None:
        return False

    db.delete(member)
    return True
