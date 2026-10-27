"""Split payment status state machine. Self-reported, then acknowledged by the bill owner.

All transitions are called through authenticated membership checks and a locked
session row. Events and notifications commit in the same transaction.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from app.models.payment_confirmation_event import PaymentConfirmationEvent
from app.models.split_bill_participant import SplitBillParticipant
from app.react_app.bill_service import get_split_bill_session_summary

PAYMENT_METHODS = {'bank_transfer', 'revolut', 'payment_link', 'cash'}
EVENT_TYPES = {'reported', 'withdrawn', 'received', 'receipt_reversed', 'reopened_reset', 'reminder_reset'}


def record_event(db, session, participant, actor_user_id, kind):
    if kind not in EVENT_TYPES:
        raise ValueError('Invalid payment event.')
    snapshot = get_split_bill_session_summary(db, session, ensure_translations=False)
    row = next((x for x in snapshot['participants'] if x['participant_id'] == participant.id), None)
    amount = Decimal(str(row['total'] if row else 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    db.add(PaymentConfirmationEvent(session_id=session.id, participant_id=participant.id,
        actor_user_id=actor_user_id, event_type=kind, method=participant.payment_method,
        amount=amount, currency=session.currency))


def acknowledge(db, session, participant_id, owner_user_id, *, reverse=False):
    if session.owner_user_id != owner_user_id:
        raise PermissionError('Only the bill owner can acknowledge a payment.')
    if session.status not in {'settled', 'closed'}:
        raise ValueError('Settle the split before confirming payments.')
    participant = db.query(SplitBillParticipant).filter_by(id=participant_id, session_id=session.id,
         status='joined').with_for_update().first()
    if not participant or participant.role == 'owner' or not participant.user_id:
        raise ValueError('Choose a joined participant with an account.')
    state = participant.payment_status or 'unpaid'
    if reverse:
        if state == 'paid':
            return False  # Idempotent reversal, never re-notify.
        if state != 'received':
            raise ValueError('Only received payments can be reversed.')
        participant.payment_status = 'paid'
        participant.received_at = None
        participant.confirmed_by_user_id = None
        kind = 'receipt_reversed'
    else:
        if state == 'received':
            return False  # Idempotent repeated confirm.
        if state != 'paid':
            raise ValueError('A participant must report payment before the owner confirms receipt.')
        participant.payment_status = 'received'
        participant.received_at = datetime.utcnow()
        participant.confirmed_by_user_id = owner_user_id
        kind = 'received'
    record_event(db, session, participant, owner_user_id, kind)
    from app.react_app.events import enqueue_payment_confirmation
    enqueue_payment_confirmation(db, session, participant, kind)
    db.commit()
    return True


def withdraw(db, session, participant_id, user_id):
    if session.status not in {'settled', 'closed'}:
        raise ValueError('Settle the split before updating payments.')
    participant = db.query(SplitBillParticipant).filter_by(id=participant_id, session_id=session.id,
        status='joined', user_id=user_id).with_for_update().first()
    if not participant or participant.role == 'owner':
        raise PermissionError('Only a participant can withdraw their own payment report.')
    if participant.payment_status in {'unpaid', 'initiated', None}:
        return False
    if participant.payment_status == 'received':
        raise ValueError('Ask the owner to reverse their receipt confirmation first.')
    if participant.payment_status != 'paid':
        raise ValueError('Unrecognized payment state.')
    record_event(db, session, participant, user_id, 'withdrawn')
    participant.payment_status = 'unpaid'
    participant.payment_method = None
    participant.paid_at = None
    from app.react_app.events import enqueue_payment_confirmation
    enqueue_payment_confirmation(db, session, participant, 'withdrawn')
    db.commit()
    return True


def history(db, session, limit=100):
    rows = (db.query(PaymentConfirmationEvent)
        .filter(PaymentConfirmationEvent.session_id == session.id)
        .order_by(PaymentConfirmationEvent.id.desc()).limit(min(max(int(limit), 1), 100)).all())
    members = {p.id:p for p in db.query(SplitBillParticipant).filter_by(session_id=session.id).all()}
    return [{'id':row.id, 'event_type':row.event_type,
             'participant_id':row.participant_id,
             'participant_name':(members[row.participant_id].display_name if row.participant_id in members else 'Former participant'),
             'actor_role':'owner' if row.actor_user_id == session.owner_user_id else 'participant',
             'method':row.method, 'amount':str(row.amount), 'currency':row.currency,
             'created_at':row.created_at.isoformat() + 'Z' if row.created_at else None}
            for row in rows]
