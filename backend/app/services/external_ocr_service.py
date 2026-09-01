import json
import os
from time import perf_counter
from app.models.receipt_item import ReceiptItem
from app.schemas.external_ocr import ExternalOCRMockResult, ExternalOCRProviderUpdate

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.external_ocr_request import ExternalOCRRequest
from app.models.document import Document
from app.models.external_ocr_usage import ExternalOCRUsage
from app.services.receipt_quality_service import calculate_items_name_quality

from app.services.document_service import get_document_by_id
from app.services.ocr_providers.provider_router import (
    choose_provider_name,
    process_external_ocr_with_provider,
    list_configured_providers,
    get_provider
)

def create_external_ocr_usage_log(
    db: Session,
    request: ExternalOCRRequest,
    provider: str,
    status: str,
    duration_ms: int | None = None,
    provider_result=None,
    validation: dict | None = None,
    items_count: int = 0,
    error_message: str | None = None
):
    usage = ExternalOCRUsage(
        external_ocr_request_id=request.id,
        document_id=request.document_id,
        case_id=request.case_id,
        provider=provider,
        status=status,
        pages_processed=getattr(provider_result, "pages_processed", 1) if provider_result else 1,
        items_count=items_count,
        receipt_total=getattr(provider_result, "receipt_total", None) if provider_result else None,
        provider_confidence=getattr(provider_result, "provider_confidence", None) if provider_result else None,
        validation_is_valid=validation.get("is_valid") if validation else None,
        duration_ms=duration_ms,
        error_message=error_message
    )

    db.add(usage)
    db.commit()
    db.refresh(usage)

    return usage

def get_external_ocr_usage_logs(
    db: Session,
    limit: int = 100
):
    return (
        db.query(ExternalOCRUsage)
        .order_by(ExternalOCRUsage.created_at.desc())
        .limit(limit)
        .all()
    )

def process_external_ocr_request_with_router(
    db: Session,
    request: ExternalOCRRequest
):
    start_time = perf_counter()
    provider_name = request.preferred_provider or "unknown"

    document = get_document_by_id(
        db=db,
        document_id=request.document_id
    )

    if not document:
        fail_external_ocr_request(
            db=db,
            request=request,
            error_message="Document not found for external OCR request."
        )

        raise ValueError("Document not found for external OCR request.")

    try:
        provider_name = choose_provider_name(request)

        assert_external_ocr_usage_allowed(
            db=db,
            provider=provider_name
        )

        mark_external_ocr_processing(
            db=db,
            request=request,
            provider=provider_name
        )

        provider_result = process_external_ocr_with_provider(
            document=document,
            request=request
        )

        validation = validate_external_ocr_result(provider_result)

        external_result_json = provider_result.model_dump()
        external_result_json["validation"] = validation

        duration_ms = int((perf_counter() - start_time) * 1000)

        if not validation["is_valid"]:
            reviewed_request = mark_external_ocr_needs_review(
                db=db,
                request=request,
                external_result=external_result_json,
                error_message="External OCR provider result failed validation."
            )

            create_external_ocr_usage_log(
                db=db,
                request=reviewed_request,
                provider=provider_name,
                status="needs_review",
                duration_ms=duration_ms,
                provider_result=provider_result,
                validation=validation,
                items_count=0,
                error_message="External OCR provider result failed validation."
            )

            return {
                "request": reviewed_request,
                "items": [],
                "validation": validation,
                "items_replaced": False
            }

        saved_items = replace_receipt_items_from_external_result(
            db=db,
            request=request,
            external_result=provider_result
        )

        completed_request = complete_external_ocr_request(
            db=db,
            request=request,
            external_result=external_result_json
        )

        create_external_ocr_usage_log(
            db=db,
            request=completed_request,
            provider=provider_name,
            status="completed",
            duration_ms=duration_ms,
            provider_result=provider_result,
            validation=validation,
            items_count=len(saved_items),
            error_message=None
        )

        return {
            "request": completed_request,
            "items": saved_items,
            "validation": validation,
            "items_replaced": True
        }

    except ExternalOCRUsageLimitError:
        raise

    except Exception as error:
        duration_ms = int((perf_counter() - start_time) * 1000)

        failed_request = fail_external_ocr_request(
            db=db,
            request=request,
            error_message=str(error)
        )

        create_external_ocr_usage_log(
            db=db,
            request=failed_request,
            provider=provider_name,
            status="failed",
            duration_ms=duration_ms,
            provider_result=None,
            validation=None,
            items_count=0,
            error_message=str(error)
        )

        return {
            "request": failed_request,
            "items": [],
            "validation": None,
            "items_replaced": False
        }

def validate_external_ocr_result(
    external_result: ExternalOCRMockResult
) -> dict:
    items_total = round(
        sum(item.total_price for item in external_result.items),
        2
    )

    receipt_total = round(external_result.receipt_total, 2)

    total_difference = round(
        abs(items_total - receipt_total),
        2
    )

    name_quality = calculate_items_name_quality(
        [
            {
                "name": item.name,
                "total_price": item.total_price
            }
            for item in external_result.items
        ]
    )

    warnings = []

    if total_difference > 0.05:
        warnings.append(
            f"External OCR items total ({items_total}) does not match receipt total ({receipt_total})."
        )

    if name_quality < 0.70:
        warnings.append(
            f"External OCR product name quality is low ({name_quality})."
        )

    if external_result.provider_confidence < 0.75:
        warnings.append(
            f"External OCR provider confidence is low ({external_result.provider_confidence})."
        )

    is_valid = (
        total_difference <= 0.05
        and name_quality >= 0.70
        and external_result.provider_confidence >= 0.75
        and len(external_result.items) > 0
    )

    return {
        "is_valid": is_valid,
        "items_total": items_total,
        "receipt_total": receipt_total,
        "total_difference": total_difference,
        "name_quality": name_quality,
        "provider_confidence": external_result.provider_confidence,
        "warnings": warnings
    }

def mark_external_ocr_needs_review(
    db: Session,
    request: ExternalOCRRequest,
    external_result: dict,
    error_message: str
):
    request.provider_status = "needs_review"
    request.external_result_json = json.dumps(
        external_result,
        ensure_ascii=False
    )
    request.error_message = error_message
    request.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(request)

    return request

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

    validation = validate_external_ocr_result(mock_result)

    external_result_json = mock_result.model_dump()
    external_result_json["validation"] = validation

    if not validation["is_valid"]:
        reviewed_request = mark_external_ocr_needs_review(
            db=db,
            request=request,
            external_result=external_result_json,
            error_message="External OCR result failed validation."
        )

        return {
            "request": reviewed_request,
            "items": [],
            "validation": validation,
            "items_replaced": False
        }

    saved_items = replace_receipt_items_from_external_result(
        db=db,
        request=request,
        external_result=mock_result
    )

    completed_request = complete_external_ocr_request(
        db=db,
        request=request,
        external_result=external_result_json
    )

    return {
        "request": completed_request,
        "items": saved_items,
        "validation": validation,
        "items_replaced": True
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

def reset_external_ocr_request(
    db: Session,
    request: ExternalOCRRequest
):
    """
    Dev-only reset.

    Allows retesting the same external OCR request without deleting the DB.
    This does not restore the previous local OCR receipt items.
    It only resets the external OCR request status.
    """

    request.provider_status = "pending"
    request.preferred_provider = None
    request.external_result_json = None
    request.error_message = None
    request.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(request)

    return request

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

def get_available_external_ocr_providers():
    return list_configured_providers()

def update_external_ocr_request_provider(
    db: Session,
    request: ExternalOCRRequest,
    provider_data: ExternalOCRProviderUpdate
):
    provider_name = provider_data.preferred_provider

    if provider_name:
        # Validate provider exists before saving it.
        get_provider(provider_name)

    request.preferred_provider = provider_name
    request.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(request)

    return request

class ExternalOCRUsageLimitError(Exception):
    """
    Raised when external OCR processing is blocked by usage limits.
    Example: daily Azure OCR call limit reached.
    """
    pass


def get_external_ocr_daily_limits():
    max_calls = int(
        os.getenv("MAX_EXTERNAL_OCR_CALLS_PER_DAY", "20")
    )

    max_pages = int(
        os.getenv("MAX_EXTERNAL_OCR_PAGES_PER_DAY", "50")
    )

    return {
        "max_calls_per_day": max_calls,
        "max_pages_per_day": max_pages
    }


def get_external_ocr_usage_today(
    db: Session,
    provider: str | None = None
):
    today_start = datetime.utcnow().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    query = db.query(ExternalOCRUsage).filter(
        ExternalOCRUsage.created_at >= today_start
    )

    if provider:
        query = query.filter(
            ExternalOCRUsage.provider == provider
        )

    total_calls = query.count()

    total_pages = (
        query.with_entities(
            func.coalesce(func.sum(ExternalOCRUsage.pages_processed), 0)
        )
        .scalar()
        or 0
    )

    return {
        "date_utc": today_start.date().isoformat(),
        "provider": provider,
        "calls_today": total_calls,
        "pages_today": int(total_pages)
    }


def assert_external_ocr_usage_allowed(
    db: Session,
    provider: str
):
    """
    Applies limits only to real paid providers.
    Mock provider is ignored because it does not call Azure.
    """

    if provider == "mock_external_ocr":
        return

    external_ocr_enabled = os.getenv(
        "ENABLE_EXTERNAL_OCR",
        "true"
    ).lower()

    if external_ocr_enabled not in ["true", "1", "yes"]:
        raise ExternalOCRUsageLimitError(
            "External OCR is disabled by ENABLE_EXTERNAL_OCR."
        )

    limits = get_external_ocr_daily_limits()
    usage = get_external_ocr_usage_today(
        db=db,
        provider=provider
    )

    if usage["calls_today"] >= limits["max_calls_per_day"]:
        raise ExternalOCRUsageLimitError(
            f"Daily external OCR call limit reached for provider '{provider}'. "
            f"Used {usage['calls_today']} / {limits['max_calls_per_day']} calls."
        )

    if usage["pages_today"] >= limits["max_pages_per_day"]:
        raise ExternalOCRUsageLimitError(
            f"Daily external OCR page limit reached for provider '{provider}'. "
            f"Used {usage['pages_today']} / {limits['max_pages_per_day']} pages."
        )

def get_external_ocr_usage_summary(
    db: Session,
    days: int = 30
):
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            ExternalOCRUsage.provider,
            ExternalOCRUsage.status,
            func.count(ExternalOCRUsage.id).label("requests_count"),
            func.coalesce(func.sum(ExternalOCRUsage.pages_processed), 0).label("pages_processed"),
            func.coalesce(func.sum(ExternalOCRUsage.items_count), 0).label("items_extracted"),
            func.coalesce(func.avg(ExternalOCRUsage.duration_ms), 0).label("avg_duration_ms")
        )
        .filter(ExternalOCRUsage.created_at >= since)
        .group_by(
            ExternalOCRUsage.provider,
            ExternalOCRUsage.status
        )
        .all()
    )

    breakdown = []

    total_requests = 0
    total_pages = 0
    total_items = 0

    for row in rows:
        requests_count = int(row.requests_count or 0)
        pages_processed = int(row.pages_processed or 0)
        items_extracted = int(row.items_extracted or 0)

        total_requests += requests_count
        total_pages += pages_processed
        total_items += items_extracted

        breakdown.append(
            {
                "provider": row.provider,
                "status": row.status,
                "requests_count": requests_count,
                "pages_processed": pages_processed,
                "items_extracted": items_extracted,
                "avg_duration_ms": round(float(row.avg_duration_ms or 0), 2)
            }
        )

    return {
        "period_days": days,
        "since_utc": since.isoformat(),
        "totals": {
            "requests_count": total_requests,
            "pages_processed": total_pages,
            "items_extracted": total_items
        },
        "daily_limits": get_external_ocr_daily_limits(),
        "today": {
            "azure_receipt": get_external_ocr_usage_today(
                db=db,
                provider="azure_receipt"
            ),
            "mock_external_ocr": get_external_ocr_usage_today(
                db=db,
                provider="mock_external_ocr"
            )
        },
        "breakdown": breakdown
    }