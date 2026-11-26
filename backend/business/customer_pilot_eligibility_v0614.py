"""Business-authoritative customer eligibility for receipt rewards.

Authenticated Core customers are matched by the stable, signed Business
customer identity and live membership. The *merchant* is approved through
the audited v0.6.12 Business pilot enrollment table.

No customer account IDs, email addresses, or ad hoc allowlists are needed
in deployment environment variables.
"""
import os
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Membership, Program, Store
from .security import customer_actor
from .pilot_enrollment_v0612 import merchant_pilot_allowed

router = APIRouter(tags=['Customer receipt eligibility'])


@router.get('/v1/customer/pilot/receipt-eligibility-v0614')
def receipt_eligibility(
    consumer_id: str = Depends(customer_actor),
    db: Session = Depends(get_db),
):
    # This endpoint is called server-to-server with a signed Core identity;
    # it never accepts an arbitrary user ID as a query parameter.
    if os.getenv('PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED', 'false').lower() != 'true':
        return {'eligible': False, 'reason': 'receipt_pilot_disabled'}

    # Only joined, published programs at active stores are candidates.
    # An administrator's approval of the *merchant* is also mandatory.
    merchant_ids = db.scalars(
        select(Program.merchant_id)
        .join(Membership, Membership.program_id == Program.id)
        .join(Store, Store.id == Program.store_id)
        .where(
            Membership.consumer_id == consumer_id,
            Program.status == 'published',
            Store.active.is_(True),
        )
        .distinct()
    ).all()

    from .pilot_readiness_v069 import merchant_receipt_report
    for merchant_id in merchant_ids:
        if merchant_pilot_allowed(db, merchant_id) and merchant_receipt_report(db, merchant_id)['receipt_review_ready']:
            return {'eligible': True, 'reason': 'joined_approved_merchant'}

    return {'eligible': False, 'reason': 'no_joined_approved_merchant'}
