"""Small, explicit authorization rules for user-owned Pruvs resources.

Keep checks server-side: numeric IDs, tokens and request bodies never grant
access by themselves. Tests use real ORM sessions and cross-user fixtures.
"""
from datetime import datetime

from fastapi import HTTPException
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant


def joined_member(db, session_id: int, user_id: int):
    """Return an active member of exactly this session or None."""
    return (db.query(SplitBillParticipant)
            .filter_by(session_id=session_id, user_id=user_id, status='joined')
            .first())


def require_bill_access(db, token: str, user_id: int, *, owner=False, lock=False):
    """404 for missing/foreign bills; 403 for an authenticated member's owner action."""
    query = db.query(SplitBillSession).filter_by(token=token)
    session = (query.with_for_update() if lock else query).first()
    if not session:
        raise HTTPException(404, 'Bill not found.')
    participant = joined_member(db, session.id, user_id)
    if participant is None:
        raise HTTPException(404, 'Bill not found.')
    if owner and session.owner_user_id != user_id:
        raise HTTPException(403, 'Only the bill owner can perform this action.')
    return session, participant


def invitation_is_current(session: SplitBillSession, *, now=None) -> bool:
    """Seven-day invitations expire; existing members may still view the bill."""
    now = now or datetime.utcnow()
    return bool(session and (session.expires_at is None or session.expires_at > now))
