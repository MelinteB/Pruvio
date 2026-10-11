"""Incoming split events; enqueue in the same transaction as the bill transition."""
from app.services.push_service import enqueue
from app.models.split_bill_participant import SplitBillParticipant

def enqueue_transition(db,session,actor_user_id,kind):
    if kind not in ('split_settled','split_reopened') or session.owner_user_id!=actor_user_id:
        raise ValueError('Invalid split transition.')
    title,body=(('Split bill settled','The bill owner settled your shared bill. Open Pruvs to review your share and payment details.') if kind=='split_settled' else ('Split bill reopened','The bill owner reopened your shared bill. Review your allocation; payment statuses have reset.'))
    recipients={p.user_id for p in db.query(SplitBillParticipant).filter_by(session_id=session.id,status='joined') if p.user_id and p.user_id!=actor_user_id}
    for uid in recipients:enqueue(db,uid,kind,title,body,f'/bill/{session.token}')
