"""Clean up rejected scans and explicitly deleted receipts, without breaking shared bills."""
from fastapi import HTTPException
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.receipt_identity import ReceiptIdentity
from app.models.receipt_correction import ReceiptCorrection
from app.models.receipt_fingerprint import ReceiptFingerprint
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.external_ocr_usage import ExternalOCRUsage
from app.models.split_bill_session import SplitBillSession
from app.models.history_visibility import HistoryVisibility
from app.models.message import Message
from app.models.reminder import Reminder
from app.services.receipt_storage import delete_paid,erase_temporary

def delete_case(db,case_id,strict=True):
    case=db.get(Case,case_id)
    if not case: return
    if strict and db.query(SplitBillSession.id).filter_by(case_id=case_id).first():
        raise HTTPException(409,'This receipt has a shared split. Settle or resolve the split before permanent deletion.')
    if strict:
        from app.models.pruvs_commerce import ReceiptMark,RewardClaim
        if (db.query(ReceiptMark.id).filter_by(case_id=case_id).first() or
                db.query(RewardClaim.id).filter_by(case_id=case_id).first()):
            raise HTTPException(409,'This receipt has reward records. Resolve them before permanent deletion.')
        from app.models.expense import ExpenseReport
        # Expense snapshots may embed receipt IDs. Do not destroy active report evidence.
        for report in db.query(ExpenseReport).filter_by(user_id=case.user_id).all():
            if ('"case_id":'+str(case_id)) in (report.snapshot_json or '').replace(' ',''):
                raise HTTPException(409,'This receipt is used by an expense report. Remove it from the report before deleting.')
    docs=db.query(Document).filter_by(case_id=case_id).all()
    from app.services.account_deletion import validate_cloud_document
    for doc in docs:
        validate_cloud_document(doc, case.user_id, case_id)
    paths = [doc.path for doc in docs]
    # On deletion, remote object removal must succeed before database mutation.
    for doc in docs:delete_paid(doc)
    db.query(ExternalOCRUsage).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(ExternalOCRRequest).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(ReceiptCorrection).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(ReceiptItem).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(ReceiptFingerprint).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(ReceiptIdentity).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(Message).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(Reminder).filter_by(case_id=case_id).delete(synchronize_session=False)
    db.query(HistoryVisibility).filter_by(user_id=case.user_id,kind='receipt',source_id=case_id).delete(synchronize_session=False)
    for doc in docs:db.delete(doc)
    db.delete(case)
    db.commit()
    from types import SimpleNamespace
    for path in paths:
        erase_temporary(SimpleNamespace(path=path))
