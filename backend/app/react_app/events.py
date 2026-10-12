"""Incoming split events; enqueue in the same transaction as the bill transition."""
from app.services.push_service import enqueue
from app.models.user import User
from app.react_app.receipt_labels import receipt_label

def enqueue_transition(db,session,actor_user_id,kind):
    if kind not in ('split_settled','split_reopened') or session.owner_user_id!=actor_user_id:
        raise ValueError('Invalid split transition.')
    from app.react_app.bill_service import get_split_bill_session_summary
    name = receipt_label(db, session.case_id)
    owner = db.get(User, actor_user_id)
    actor = (owner.name or 'The owner') if owner else 'The owner'
    summary = get_split_bill_session_summary(db, session, ensure_translations=False)
    title = f"Split {'settled' if kind == 'split_settled' else 'reopened'} · {name}"
    for participant in summary['participants']:
        uid = participant['user_id']
        if not uid or uid == actor_user_id:
            continue
        share = f"{participant['total']:.2f} {session.currency}"
        body = (f'{actor} settled {name}. Your share: {share}, including '
                f"{participant['tip_share']:.2f} {session.currency} tip. Review payment details."
                if kind == 'split_settled' else
                f'{actor} reopened {name}. Your current allocation: {share}. '
                'Payment statuses were reset; review any changes before paying.')
        enqueue(db, uid, kind, title, body, f'/bill/{session.token}')
