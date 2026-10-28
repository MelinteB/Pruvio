"""Authenticated, deliberately scoped personal activity snapshot.

This is *not* a full data-subject-access package. It contains account profile,
owned scan/item metadata, the user's split participation, and payment events
about that participation. No authentication tokens, device subscriptions, other
participants' contacts, or receipt image bytes are included.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from app.models.case import Case
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.payment_confirmation_event import PaymentConfirmationEvent

MAX_EXPORT_ROWS = 5000


def iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def bounded(rows):
    """Avoid silently returning an incomplete export or materializing unlimited data."""
    result = rows.limit(MAX_EXPORT_ROWS + 1).all()
    if len(result) > MAX_EXPORT_ROWS:
        raise HTTPException(413, 'Your activity exceeds the export limit. Contact support for a complete export.')
    return result


def snapshot(db, user):
    uid = user.id  # Only the authenticated account is ever used as a filter.
    cases = bounded(db.query(Case).filter(Case.user_id == uid).order_by(Case.id))
    items = bounded(db.query(ReceiptItem).join(Case, ReceiptItem.case_id == Case.id)
                    .filter(Case.user_id == uid).order_by(ReceiptItem.id))
    participations = bounded(db.query(SplitBillParticipant, SplitBillSession)
        .join(SplitBillSession, SplitBillParticipant.session_id == SplitBillSession.id)
        .filter(SplitBillParticipant.user_id == uid)
        .order_by(SplitBillSession.id, SplitBillParticipant.id))
    events = bounded(db.query(PaymentConfirmationEvent, SplitBillParticipant)
        .join(SplitBillParticipant, PaymentConfirmationEvent.participant_id == SplitBillParticipant.id)
        .filter(SplitBillParticipant.user_id == uid,
                PaymentConfirmationEvent.session_id == SplitBillParticipant.session_id)
        .order_by(PaymentConfirmationEvent.id))

    profile_fields = ('id', 'name', 'username', 'email', 'phone_number', 'preferred_language',
        'notifications_opt_in', 'marketing_opt_in', 'is_email_verified', 'is_phone_verified',
        'accepted_terms_at', 'terms_version', 'accepted_privacy_at', 'privacy_version',
        'created_at', 'updated_at')
    account = {field: (iso(getattr(user, field, None)) if field.endswith('_at') else getattr(user, field, None))
               for field in profile_fields}
    # These are the requesting user's own saved payment preferences.
    account['my_payment_preferences'] = {key: getattr(user, key, None) for key in (
        'payment_recipient_name', 'payment_iban', 'payment_bank_name', 'payment_bic',
        'revolut_payment_link', 'payment_note')}

    return {
        'format': 'pruvs-account-activity-v1',
        'exported_at': iso(datetime.now(timezone.utc)),
        'scope_note': ('Account activity snapshot only. Does not include raw receipt images, '
            'authentication credentials, push device identifiers, or every record held by Pruvs. '
            'Contact support for a broader personal data access request.'),
        'account': account,
        'owned_scans': [{'case_id': c.id, 'module': c.module, 'status': c.status,
                         'created_at': iso(c.created_at)} for c in cases],
        'owned_receipt_items': [{'item_id': i.id, 'case_id': i.case_id, 'name': i.name,
            'translated_name': i.translated_name, 'quantity': i.quantity,
            'unit_price': i.unit_price, 'total_price': i.total_price,
            'currency': i.currency, 'created_at': iso(i.created_at)} for i in items],
        'my_bill_participation': [{'bill_id': s.id, 'role': p.role,
            'bill_status': s.status, 'currency': s.currency,
            'payment_status': p.payment_status, 'payment_method': p.payment_method,
            'reported_at': iso(p.paid_at), 'received_at': iso(p.received_at),
            'created_at': iso(s.created_at)} for p, s in participations],
        'my_payment_history': [{'event_id': e.id, 'bill_id': e.session_id,
            'event_type': e.event_type, 'actor_role': (
                'self' if e.actor_user_id == uid else 'bill_owner_or_other'),
            'method': e.method, 'amount': str(e.amount), 'currency': e.currency,
            'created_at': iso(e.created_at)} for e, p in events],
    }
