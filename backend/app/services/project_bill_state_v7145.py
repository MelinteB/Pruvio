"""Bill-level Project display state; payment confirmation is authoritative.

This module uses only caller-supplied totals/payment states, so the status is
recomputed from source bill records whenever a Project snapshot is requested.
"""
from decimal import Decimal, InvalidOperation


def split_state(remaining_total, participants, owner_id):
    try:
        remaining = Decimal(str(remaining_total))
    except (InvalidOperation, TypeError, ValueError):
        return 'unallocated'
    allocated = bool(participants) and remaining >= 0 and remaining < Decimal('0.005')
    if not allocated:
        return 'unallocated'
    # A paid bill is NEVER inferred from its allocation or from split status.
    for person in participants:
        amount = Decimal(str(person.get('total') or 0))
        if amount >= Decimal('0.005') and person.get('user_id') != owner_id:
            if str(person.get('payment_status') or '').lower() != 'received':
                return 'allocated'
    return 'confirmed'


def project_share_state(shares):
    if not shares:
        return 'unallocated'
    for share in shares:
        if share.user_id != share.paid_by_user_id and share.amount_minor > 0:
            if share.payment_status != 'confirmed':
                return 'allocated'
    return 'confirmed'
