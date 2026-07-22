import json

from app.models.receipt_item import ReceiptItem
from app.schemas.external_ocr import ExternalOCRMockResult


from datetime import datetime
from sqlalchemy.orm import Session

from app.models.external_ocr_request import ExternalOCRRequest
from app.models.document import Document

def mark_external_ocr_processing(
    db: Session,
    request: ExternalOCRRequest,
    provider: str
):
    request.provider_status = "processing"
    request.preferred_provider = provider
    request.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(request)

    return request


def complete_external_ocr_request(
    db: Session,
    request: ExternalOCRRequest,
    external_result: dict
):
    request.provider_status = "completed"
    request.external_result_json = json.dumps(
        external_result,
        ensure_ascii=False
    )
    request.error_message = None
    request.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(request)

    return request


def fail_external_ocr_request(
    db: Session,
    request: ExternalOCRRequest,
    error_message: str
):
    request.provider_status = "failed"
    request.error_message = error_message
    request.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(request)

    return request


def replace_receipt_items_from_external_result(
    db: Session,
    request: ExternalOCRRequest,
    external_result: ExternalOCRMockResult
):
    db.query(ReceiptItem).filter(
        ReceiptItem.document_id == request.document_id
    ).delete()

    saved_items = []

    for item in external_result.items:
        unit_price = item.unit_price

        if unit_price is None:
            unit_price = item.total_price / item.quantity

        receipt_item = ReceiptItem(
            case_id=request.case_id,
            document_id=request.document_id,
            name=item.name,
            quantity=item.quantity,
            unit_price=round(unit_price, 2),
            total_price=item.total_price,
            currency=item.currency,
            selected_by_user=False
        )

        db.add(receipt_item)
        saved_items.append(receipt_item)

    db.commit()

    for item in saved_items:
        db.refresh(item)

    return saved_items


def process_mock_external_ocr_result(
    db: Session,
    request: ExternalOCRRequest,
    mock_result: ExternalOCRMockResult
):
    mark_external_ocr_processing(
        db=db,
        request=request,
        provider=mock_result.provider
    )

    saved_items = replace_receipt_items_from_external_result(
        db=db,
        request=request,
        external_result=mock_result
    )

    external_result_json = mock_result.model_dump()

    completed_request = complete_external_ocr_request(
        db=db,
        request=request,
        external_result=external_result_json
    )

    return {
        "request": completed_request,
        "items": saved_items
    }


def get_external_ocr_requests(db: Session):
    return (
        db.query(ExternalOCRRequest)
        .order_by(ExternalOCRRequest.created_at.desc())
        .all()
    )


def get_external_ocr_request_by_id(
    db: Session,
    request_id: int
):
    return (
        db.query(ExternalOCRRequest)
        .filter(ExternalOCRRequest.id == request_id)
        .first()
    )


def get_pending_external_ocr_requests(db: Session):
    return (
        db.query(ExternalOCRRequest)
        .filter(ExternalOCRRequest.provider_status == "pending")
        .order_by(ExternalOCRRequest.created_at.asc())
        .all()
    )


def get_external_ocr_request_by_document(
    db: Session,
    document_id: int
):
    return (
        db.query(ExternalOCRRequest)
        .filter(
            ExternalOCRRequest.document_id == document_id,
            ExternalOCRRequest.provider_status.in_(
                ["pending", "processing", "completed"]
            )
        )
        .order_by(ExternalOCRRequest.created_at.desc())
        .first()
    )


def create_external_ocr_request_if_needed(
    db: Session,
    document: Document,
    extraction_result: dict
):
    if not extraction_result.get("external_ocr_recommended"):
        return None, False

    existing_request = get_external_ocr_request_by_document(
        db=db,
        document_id=document.id
    )

    if existing_request:
        return existing_request, False

    request = ExternalOCRRequest(
        document_id=document.id,
        case_id=document.case_id,
        reason="local_ocr_quality_low",
        provider_status="pending",
        preferred_provider=None,
        local_confidence=extraction_result.get("confidence"),
        local_name_quality=extraction_result.get("name_quality"),
        local_detected_total=extraction_result.get("detected_total"),
        local_receipt_total=extraction_result.get("receipt_total"),
        updated_at=datetime.utcnow()
    )

    db.add(request)
    db.commit()
    db.refresh(request)

    return request, True