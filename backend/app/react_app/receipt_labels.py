"""Short merchant label for joined split participants and History group headings."""
from app.models.external_ocr_request import ExternalOCRRequest
from app.services.standalone_app_service import _parse_ocr_metadata


def receipt_label(db, case_id):
    request = (db.query(ExternalOCRRequest)
               .filter_by(case_id=case_id)
               .order_by(ExternalOCRRequest.id.desc()).first())
    value = _parse_ocr_metadata(request).get('merchant_name')
    merchant = value.strip() if isinstance(value, str) else ''
    return merchant[:180] if merchant else f'Receipt #{case_id}'


def receipt_labels(db, case_ids):
    """Load latest merchant OCR metadata for a page of receipts in one SQL query.

    Expects a bounded collection (History uses a page of at most 30 groups).
    The latest OCR request wins, matching receipt_label() behavior.
    """
    ids = tuple(dict.fromkeys(int(case_id) for case_id in case_ids))
    if not ids:
        return {}
    results = {case_id: f'Receipt #{case_id}' for case_id in ids}
    records = (db.query(ExternalOCRRequest)
               .filter(ExternalOCRRequest.case_id.in_(ids))
               .order_by(ExternalOCRRequest.id.desc()).all())
    seen = set()
    for record in records:
        if record.case_id in seen or record.case_id not in results:
            continue
        seen.add(record.case_id)
        value = _parse_ocr_metadata(record).get('merchant_name')
        merchant = value.strip() if isinstance(value, str) else ''
        if merchant:
            results[record.case_id] = merchant[:180]
    return results
