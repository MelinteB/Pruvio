"""Owner-only removal from an open split, preserving historical membership.

The API holds the session row lock before calling this function. The participant
row is also locked. Any failure rolls back the assignment release and Inbox event.
"""
from fastapi import HTTPException
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.user import User
from app.models.push_notification import PushEvent
from app.services.push_service import enqueue


def remove_participant(db, session, actor_id: int, participant_id: int):
    if type(participant_id) is not int or participant_id <= 0:
        raise HTTPException(400, 'Choose a valid participant.')
    if session.owner_user_id != actor_id:
        raise HTTPException(403, 'Only the bill owner can remove participants.')
    if session.status != 'open':
        raise HTTPException(409, 'Reopen the split before removing participants.')
    person = (db.query(SplitBillParticipant)
              .filter_by(session_id=session.id, id=participant_id)
              .with_for_update().first())
    if not person or person.status != 'joined':
        raise HTTPException(404, 'Active participant not found.')
    if person.role == 'owner' or person.user_id == session.owner_user_id:
        raise HTTPException(403, 'The bill owner cannot be removed.')
    if (person.payment_status or 'unpaid') != 'unpaid' or person.paid_at or person.received_at:
        raise HTTPException(409, 'Payment activity exists. Resolve the payment before removing this participant.')

    # Quantities become available for remaining members to claim. No other
    # participant's assignments, payment details, or historic membership change.
    db.query(SplitBillItemAssignment).filter_by(
        session_id=session.id, participant_id=person.id
    ).delete(synchronize_session=False)
    # An earlier pending bill notification must not be delivered with sensitive
    # details after access revocation. A worker already sending is outside this
    # transaction; the in-app history is independently redacted on every read.
    for old in db.query(PushEvent).filter(
        PushEvent.user_id == person.user_id,
        PushEvent.url == '/bill/' + session.token,
        PushEvent.status == 'pending',
    ).all() if person.user_id else []:
        old.title = 'Previous bill activity'
        old.body = 'This bill is no longer available to your account.'
        old.url = '/history'
        old.status = 'in_app_only'
    person.status = 'removed'
    person.reminder_message = None
    person.reminder_at = None

    # A revoked account must not receive a push/inbox payload with the merchant,
    # receipt title, token, owner name, amount or other members' details.
    recipient = db.get(User, person.user_id) if person.user_id else None
    if recipient and recipient.status == 'active':
        ro = recipient.preferred_language == 'ro'
        enqueue(db, recipient.id, 'participant_removed',
                'Acces la nota comună revocat' if ro else 'Shared bill access removed',
                'Organizatorul te-a eliminat dintr-o notă comună. Nu mai poți accesa nota sau reutiliza invitația.' if ro else
                'The bill owner removed you from a shared bill. You can no longer open it or reuse the invitation.',
                '/history')
    db.commit()
    return person.id
