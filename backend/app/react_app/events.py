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
    for participant in summary['participants']:
        uid = participant['user_id']
        if not uid or uid == actor_user_id:
            continue
        recipient = db.get(User, uid)
        ro = recipient and recipient.preferred_language == 'ro'
        share = f"{participant['total']:.2f} {session.currency}"
        if ro:
            title = f"{'Notă închisă' if kind == 'split_settled' else 'Notă redeschisă'} · {name}"
            body = (f'{actor} a închis nota {name}. Cota ta: {share}, inclusiv '
                    f"{participant['tip_share']:.2f} {session.currency} bacșiș. Verifică detaliile plății."
                    if kind == 'split_settled' else
                    f'{actor} a redeschis nota {name}. Cota ta actuală: {share}. '
                    'Plățile declarate au fost resetate; verifică modificările înainte de plată.')
        else:
            title = f"Split {'settled' if kind == 'split_settled' else 'reopened'} · {name}"
            body = (f'{actor} settled {name}. Your share: {share}, including '
                    f"{participant['tip_share']:.2f} {session.currency} tip. Review payment details."
                    if kind == 'split_settled' else
                    f'{actor} reopened {name}. Your current allocation: {share}. '
                    'Payment statuses were reset; review any changes before paying.')
        enqueue(db, uid, kind, title, body, f'/bill/{session.token}')


def enqueue_reminder(db, session, participant, *, reconfirm=False):
    recipient = db.get(User, participant.user_id)
    if not recipient:
        raise ValueError('The participant account is no longer available.')
    from app.react_app.bill_service import get_split_bill_session_summary
    summary = get_split_bill_session_summary(db, session, ensure_translations=False)
    own = next((row for row in summary['participants'] if row['participant_id'] == participant.id), None)
    share = f"{own['total']:.2f} {session.currency}" if own else session.currency
    name = receipt_label(db, session.case_id)
    custom = participant.reminder_message or ''
    defaults = ('Please complete your Pruvs split bill.', 'Please complete your Pruvs bill payment.')
    custom = '' if custom in defaults else custom
    if recipient.preferred_language == 'ro':
        title = f'Memento plată · {name}'
        body = (f'Cota ta pentru {name}: {share}. '
                + ('Organizatorul îți cere să reconfirmi plata în Pruvs.' if reconfirm else 'Verifică și achită cota ta în Pruvs.'))
    else:
        title = f'Payment reminder · {name}'
        body = (f'Your share for {name}: {share}. '
                + ('The owner asks you to reconfirm your payment in Pruvs.' if reconfirm else 'Review and pay your share in Pruvs.'))
    if custom:
        body += ' ' + custom
    enqueue(db, recipient.id, 'reminder', title, body, f'/bill/{session.token}')


def enqueue_payment_marked(db, session, participant):
    """Tell the owner about a participant's self-reported payment."""
    if not participant.user_id or participant.user_id == session.owner_user_id:
        return
    owner = db.get(User, session.owner_user_id)
    if not owner:
        return
    from app.react_app.bill_service import get_split_bill_session_summary
    summary = get_split_bill_session_summary(db, session, ensure_translations=False)
    share = next((row for row in summary['participants'] if row['participant_id'] == participant.id), None)
    amount = f"{share['total']:.2f} {session.currency}" if share else f"0.00 {session.currency}"
    name = receipt_label(db, session.case_id)
    actor = (participant.display_name or 'A participant').strip()[:120]
    if owner.preferred_language == 'ro':
        method = 'transfer bancar' if participant.payment_method == 'bank_transfer' else 'Revolut'
        title = f'Plată declarată · {name}'
        body = f'{actor} a marcat cota sa de {amount} ca plătită prin {method}. Verifică încasarea.'
    else:
        method = 'bank transfer' if participant.payment_method == 'bank_transfer' else 'Revolut'
        title = f'Payment reported · {name}'
        body = f'{actor} marked their share of {amount} as paid via {method}. Please verify receipt of the payment.'
    enqueue(db, owner.id, 'payment_marked', title, body, f'/bill/{session.token}')
