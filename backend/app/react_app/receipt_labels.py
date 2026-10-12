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
