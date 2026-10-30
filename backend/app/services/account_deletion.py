"""Account deletion preflight and storage-safe cleanup.

No scheduled erasure is enabled in this release: approved retention periods,
Stripe billing and legal-hold handling require separate operator decisions.

Cloud deletions are idempotent but cannot be made atomic with a SQL transaction.
If a provider fails, the database remains in place and the user can retry.
"""
from __future__ import annotations

import os
from fastapi import HTTPException
from sqlalchemy import or_

from app.models.case import Case
from app.models.document import Document
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.pruvs_billing import PruvsStripeAccount, PruvsStripeCheckout, PruvsInvoiceEmail


def inspect_account(db, user) -> dict:
    """Read-only, user-scoped counts; never exposes receipt/participant contact data."""
    uid = int(user.id)
    cases = db.query(Case.id).filter(Case.user_id == uid)
    owned = db.query(SplitBillSession.id).filter(or_(SplitBillSession.owner_user_id == uid,
                                                    SplitBillSession.case_id.in_(cases)))
    stripe = db.query(PruvsStripeAccount).filter_by(user_id=uid).first()
    invoice_count = db.query(PruvsInvoiceEmail).filter_by(user_id=uid).count()
    checkout_count = db.query(PruvsStripeCheckout).filter_by(user_id=uid).count()
    # The user must contact support before deleting records that may be subject
    # to billing, refund, tax or subscription obligations. Never modify Stripe here.
    billed = bool(stripe and (stripe.customer_id or stripe.subscription_id or stripe.status in ('active', 'trialing', 'past_due', 'unpaid', 'incomplete'))) or bool(invoice_count or checkout_count)
    reasons = []
    if billed:
        reasons.append('Billing records require a support review before account deletion. Contact Pruvs support.')
    # A malformed or cross-account cloud reference is a blocking storage issue,
    # and the preview should not promise successful deletion in that state.
    try:
        _objects_for_user(db, uid)
    except HTTPException:
        reasons.append('Receipt storage needs support review before account deletion.')
    # Query only the signed-in user's data, without listing names or tokens.
    result = {
        'can_delete': not reasons,
        'receipts': cases.count(),
        'receipt_documents': db.query(Document.id).filter(Document.case_id.in_(cases)).count(),
        'cloud_receipts': db.query(Document.id).filter(Document.case_id.in_(cases), Document.path.like('s3://%')).count(),
        'owned_splits': owned.distinct().count(),
        'joined_splits': db.query(SplitBillParticipant.id).filter(SplitBillParticipant.user_id == uid).count(),
        'billing_review_required': billed,
        'blockers': reasons,
        'notice': 'Deleting a shared bill may remove other participants\' access to that bill. Billing, security and backup retention is handled separately.',
    }
    return result


def validate_cloud_document(doc, user_id: int, case_id: int):
    """Allow deletion of only this user's known receipt key in the configured bucket."""
    from app.services.receipt_storage import is_cloud
    if not is_cloud(doc):
        path = str(doc.path or '')
        if path.startswith('local://'):
            return False  # Free-plan receipt: no retained original by design.
        if not path or '://' in path:
            raise HTTPException(409, 'Receipt storage path needs support review before deletion.')
        # A locally retained original can only be deleted from the approved
        # upload roots. Refuse unknown external filesystem locations.
        from pathlib import Path
        from app.services.document_service import upload_root, LEGACY_UPLOAD_ROOT
        stored = Path(path).resolve()
        if not any(stored.is_relative_to(root.resolve()) for root in (upload_root(), LEGACY_UPLOAD_ROOT)):
            raise HTTPException(409, 'Receipt storage path needs support review before deletion.')
        return False
    path = str(doc.path)
    value = path.removeprefix('s3://')
    if '/' not in value:
        raise HTTPException(409, 'Receipt storage path needs support review before deletion.')
    bucket, key = value.split('/', 1)
    filename = str(doc.stored_filename or '')
    expected = f'users/{int(user_id)}/receipts/{int(case_id)}/{filename}'
    if (not os.getenv('PRUVS_S3_BUCKET', '').strip()
        or bucket != os.getenv('PRUVS_S3_BUCKET', '').strip()
        or key != expected or not filename
        or '/' in filename or '\\' in filename or filename in ('.', '..')):
        raise HTTPException(409, 'Receipt storage path needs support review before deletion.')
    return True


def _objects_for_user(db, user_id: int):
    """Resolve cloud keys from database rows; reject malformed or cross-user paths."""
    docs = (db.query(Document, Case.id)
            .join(Case, Case.id == Document.case_id)
            .filter(Case.user_id == user_id).all())
    objects = []
    seen = set()
    for doc, case_id in docs:
        if not validate_cloud_document(doc, user_id, case_id):
            continue
        if doc.path not in seen:
            seen.add(doc.path)
            objects.append(doc)
    return objects


def deletion_plan(db, user):
    """Validate everything that can block deletion before any cloud access."""
    preview = inspect_account(db, user)
    if not preview['can_delete']:
        raise HTTPException(409, 'Account deletion needs support review. No data was deleted.')
    objects = _objects_for_user(db, int(user.id))
    return objects


def remove_cloud_objects(objects):
    """Provider failures must not be silently ignored or trigger DB deletion."""
    from app.services.receipt_storage import delete_paid
    for doc in objects:
        try:
            delete_paid(doc)
        except Exception as exc:
            # No storage URL, bucket, token, document path, or provider error leaked.
            raise HTTPException(503, 'Receipt storage deletion failed. Account remains available; retry or contact support.') from exc


def clean_dependent_records(db, user_id: int, case_ids: list[int]):
    """Remove secondary user-owned rows missing from the original delete path.

    This function does not commit. All SQL changes share the caller's transaction.
    Global provider/webhook/security logs require a separate retention review.
    """
    from app.models.receipt_identity import ReceiptIdentity
    from app.models.receipt_fingerprint import ReceiptFingerprint
    from app.models.payment_profile import PaymentProfile
    from app.models.pruvs_commerce import (DemoSubscription, CreditEntry, Referral,
        ReceiptMark, RewardClaim, RewardVoucher)
    from app.models.pruvs_usage import PruvsMeteredUse, PruvsUpgradeRequest
    from app.models.pruvs_rewards_policy import PruvsOCRBonusGrant
    from app.models.pruvs_billing import PruvsStripeAccount, PruvsStripeCheckout, PruvsInvoiceEmail
    from app.models.react_session import ReactSession, ReactChallenge
    from app.models.push_notification import PushDelivery, PushEvent, PushGrant, PushDevice, PushPreference
    from app.models.history_visibility import HistoryVisibility
    from app.models.expense import ExpenseCompany, ExpenseTripProfile, ExpenseReport
    from app.react_app.inbox import PruvsInboxRead

    for model in (ReceiptIdentity, ReceiptFingerprint):
        db.query(model).filter(or_(model.user_id == user_id, model.case_id.in_(case_ids))).delete(synchronize_session=False)
    db.query(ReceiptMark).filter(ReceiptMark.case_id.in_(case_ids)).delete(synchronize_session=False)
    db.query(RewardClaim).filter(or_(RewardClaim.user_id == user_id, RewardClaim.case_id.in_(case_ids))).delete(synchronize_session=False)
    db.query(RewardVoucher).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(DemoSubscription).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(CreditEntry).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(Referral).filter(or_(Referral.owner_id == user_id, Referral.referred_id == user_id)).delete(synchronize_session=False)
    db.query(PruvsOCRBonusGrant).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(PruvsMeteredUse).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(PruvsUpgradeRequest).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(PaymentProfile).filter_by(user_id=user_id).delete(synchronize_session=False)
    # Billing rows are only empty/unlinked at this point (see deletion_plan).
    db.query(PruvsStripeCheckout).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(PruvsInvoiceEmail).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(PruvsStripeAccount).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(ReactSession).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(ReactChallenge).filter_by(user_id=user_id).delete(synchronize_session=False)
    ids = db.query(PushEvent.id).filter_by(user_id=user_id)
    db.query(PushDelivery).filter(PushDelivery.event_id.in_(ids)).delete(synchronize_session=False)
    for model in (PushEvent, PushGrant, PushDevice, PushPreference, PruvsInboxRead,
                  HistoryVisibility, ExpenseReport, ExpenseTripProfile, ExpenseCompany):
        db.query(model).filter_by(user_id=user_id).delete(synchronize_session=False)
