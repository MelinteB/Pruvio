import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.receipt_item import ReceiptItem
from app.models.user import User
from app.services.azure_receipt_direct_service import (
    process_document_with_azure_receipt_direct,
)
from app.services.document_service import save_document_bytes
from app.services.receipt_translation_service import translate_receipt_item_names


STANDALONE_OWNER_PHONE = "web:standalone-owner"
STANDALONE_OWNER_NAME = "Pruvs User"


def get_or_create_standalone_owner(db: Session) -> User:
    """Return the MVP web-app owner used while account login is not enabled."""
    user = (
        db.query(User)
        .filter(User.phone_number == STANDALONE_OWNER_PHONE)
        .first()
    )

    if user:
        if user.status != "active" or not user.accepted_terms:
            user.status = "active"
            user.accepted_terms = True
            user.accepted_terms_at = user.accepted_terms_at or datetime.utcnow()
            db.commit()
            db.refresh(user)
        return user

    user = User(
        phone_number=STANDALONE_OWNER_PHONE,
        name=STANDALONE_OWNER_NAME,
        status="active",
        accepted_terms=True,
        accepted_terms_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_standalone_receipt_case(
    db: Session,
    *,
    file_bytes: bytes,
    original_filename: str,
    mime_type: str | None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Create a case, save the upload and immediately process it with Azure OCR."""
    if user_id is not None:
        owner = db.query(User).filter(User.id == user_id).first()
        if not owner:
            raise ValueError("Signed-in user was not found.")
    else:
        # Compatibility fallback for the development API.
        owner = get_or_create_standalone_owner(db)

    case = Case(
        user_id=owner.id,
        module="split_bill",
        status="processing",
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    try:
        document = save_document_bytes(
            db=db,
            case=case,
            file_bytes=file_bytes,
            original_filename=original_filename,
            mime_type=mime_type,
            document_type="receipt",
        )

        ocr_result = process_document_with_azure_receipt_direct(
            db=db,
            document_id=document.id,
        )

        case.status = "needs_confirmation" if ocr_result.get("is_valid") else "needs_review"
        db.commit()
        db.refresh(case)

        return {
            "case": case,
            "document": document,
            "ocr": ocr_result,
        }

    except Exception:
        case.status = "processing_failed"
        db.commit()
        raise


def ensure_receipt_translations(
    db: Session,
    items: list[ReceiptItem],
) -> None:
    """
    Backfill translations for receipts created before translation was enabled.

    Romanian and English bills keep their original names. For any other detected
    language, English translations are stored alongside the OCR original.
    """
    if not items or all(item.source_language for item in items):
        return

    translation = translate_receipt_item_names([item.name for item in items])

    if translation.error:
        # Translation is intentionally non-critical.
        print(f"Receipt translation backfill skipped: {translation.error}")
        return

    source_language = translation.source_language
    if not source_language:
        return

    for item in items:
        if not item.source_language:
            item.source_language = source_language

        translated = translation.translated_names.get(item.name)
        if translated:
            item.translated_name = translated

    db.commit()


def _latest_document_for_case(db: Session, case_id: int) -> Document | None:
    return (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.created_at.desc())
        .first()
    )


def _latest_ocr_for_case(db: Session, case_id: int) -> ExternalOCRRequest | None:
    return (
        db.query(ExternalOCRRequest)
        .filter(ExternalOCRRequest.case_id == case_id)
        .order_by(ExternalOCRRequest.created_at.desc())
        .first()
    )


def _parse_ocr_metadata(request: ExternalOCRRequest | None) -> dict[str, Any]:
    if not request or not request.external_result_json:
        return {}

    try:
        payload = json.loads(request.external_result_json)
    except Exception:
        return {}

    provider_result = payload.get("provider_result") or payload
    validation = payload.get("validation") or {}

    return {
        "merchant_name": provider_result.get("merchant_name"),
        "receipt_total": validation.get("receipt_total") or provider_result.get("receipt_total"),
        "currency": payload.get("currency_override") or provider_result.get("currency"),
        "provider_confidence": provider_result.get("provider_confidence"),
        "validation_status": validation.get("status"),
    }


def get_receipt_view(
    db: Session,
    case_id: int,
    user_id: int | None = None,
    *, ensure_translations: bool = True,
) -> dict[str, Any] | None:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return None
    if user_id is not None and case.user_id != user_id:
        return None

    items = (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == case_id)
        .order_by(ReceiptItem.id.asc())
        .all()
    )

    if ensure_translations:
        ensure_receipt_translations(db, items)

    document = _latest_document_for_case(db, case_id)
    ocr_request = _latest_ocr_for_case(db, case_id)
    metadata = _parse_ocr_metadata(ocr_request)

    currency = (
        metadata.get("currency")
        or (items[0].currency if items else None)
        or "—"
    )
    calculated_total = round(sum(float(item.total_price or 0) for item in items), 2)
    receipt_total = metadata.get("receipt_total")
    if receipt_total is None:
        receipt_total = calculated_total

    return {
        "case_id": case.id,
        "user_id": case.user_id,
        "status": case.status,
        "document_id": document.id if document else None,
        "original_filename": document.original_filename if document else None,
        "merchant_name": metadata.get("merchant_name") or "Receipt",
        "receipt_total": float(receipt_total or 0),
        "calculated_total": calculated_total,
        "currency": currency,
        "provider_confidence": metadata.get("provider_confidence"),
        "validation_status": metadata.get("validation_status"),
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "translated_name": item.translated_name,
                "source_language": item.source_language,
                "quantity": float(item.quantity or 1),
                "unit_price": (
                    float(item.unit_price)
                    if item.unit_price is not None
                    else (
                        float(item.total_price or 0) / float(item.quantity or 1)
                    )
                ),
                "total_price": float(item.total_price or 0),
                "currency": item.currency or currency,
            }
            for item in items
        ],
    }


def list_recent_receipts(
    db: Session,
    user_id: int | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    owner_id = user_id
    if owner_id is None:
        owner_id = get_or_create_standalone_owner(db).id

    cases = (
        db.query(Case)
        .filter(Case.user_id == owner_id)
        .order_by(Case.created_at.desc())
        .limit(limit)
        .all()
    )

    results: list[dict[str, Any]] = []
    for case in cases:
        items = (
            db.query(ReceiptItem)
            .filter(ReceiptItem.case_id == case.id)
            .order_by(ReceiptItem.id.asc())
            .all()
        )
        if not items:
            continue

        document = _latest_document_for_case(db, case.id)
        metadata = _parse_ocr_metadata(_latest_ocr_for_case(db, case.id))
        currency = metadata.get("currency") or items[0].currency or "—"
        total = metadata.get("receipt_total")
        if total is None:
            total = sum(float(item.total_price or 0) for item in items)

        results.append(
            {
                "case_id": case.id,
                "merchant_name": metadata.get("merchant_name") or "Receipt",
                "total": round(float(total or 0), 2),
                "currency": currency,
                "created_at": case.created_at,
                "filename": document.original_filename if document else None,
            }
        )

    return results
