"""Receipt claim review access gates for Pruvs Business v0.6.10.

A customer claim code grants a 15-minute merchant-staff review window after
successful lookup. Reissuing a code clears that authorization. No code, hash,
JWT, image, or token is returned in claim listings.
"""
from datetime import timedelta

from .models import utcnow
from .pilot_v05 import aware


def code_is_unlocked(code, staff_id, *, now=None):
    if code is None or not code.unlocked_at or code.unlocked_by_staff != staff_id:
        return False
    at = aware(code.unlocked_at)
    current = aware(now or utcnow())
    return current - timedelta(minutes=15) <= at <= current


def claim_access_flags(code, staff_id, *, pending=True, now=None):
    """Legacy claims without a customer-issued code remain reviewable."""
    needs_code = code is not None
    return {
        'requires_customer_code': needs_code,
        'review_unlocked': bool(pending and (
            not needs_code or code_is_unlocked(code, staff_id, now=now)
        )),
    }
