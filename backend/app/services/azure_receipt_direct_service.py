import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.external_ocr_request import ExternalOCRRequest
from app.services.ocr_providers.azure_receipt_provider import AzureReceiptOCRProvider


def model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")

    if hasattr(model, "dict"):
        return model.dict()

    return model

def is_discount_item(item_name: str | None) -> bool:
    if not item_name:
        return False

    normalized_name = item_name.strip().lower()

    discount_keywords = [
        "reducere",
        "reduceri",
        "discount",
        "discounts",
        "voucher",
        "coupon",
        "cupon",
        "promo",
        "promotie",
        "promotion",
        "rabatt",
    ]

    return any(
        keyword in normalized_name
        for keyword in discount_keywords
    )

def normalize_receipt_item_amounts(external_item) -> dict:
    name = external_item.name or "Unknown item"

    quantity = float(external_item.quantity or 1)

    unit_price = (
        float(external_item.unit_price)
        if external_item.unit_price is not None
        else None
    )

    total_price = float(external_item.total_price or 0)

    if is_discount_item(name):
        total_price = -abs(total_price)

        if unit_price is not None:
            unit_price = -abs(unit_price)

    return {
        "name": name,
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": total_price,
    }

def process_document_with_azure_receipt_direct(
    db: Session,
    document_id: int
) -> dict:
    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    if not document:
        raise ValueError("Document not found.")

    if not document.case_id:
        raise ValueError("Document is not linked to a case.")

    provider = AzureReceiptOCRProvider()

    if not provider.is_configured():
        raise ValueError(
            "Azure Receipt OCR provider is not configured. "
            "Check AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )

    external_request = ExternalOCRRequest(
        document_id=document.id,
        case_id=document.case_id,
        reason="direct_azure_receipt_ocr",
        provider_status="processing",
        preferred_provider="azure_receipt",
        local_confidence=None,
        local_name_quality=None,
        local_detected_total=None,
        local_receipt_total=None,
        error_message=None,
    )

    db.add(external_request)
    db.commit()
    db.refresh(external_request)

    started_at = datetime.utcnow()

    try:
        result = provider.process_document(
            document=document,
            request=external_request
        )

        result_dict = model_to_dict(result)

        db.query(ReceiptItem).filter(
            ReceiptItem.document_id == document.id
        ).delete()

        saved_items = []

        for external_item in result.items:
            normalized_item = normalize_receipt_item_amounts(external_item)

            item = ReceiptItem(
                case_id=document.case_id,
                document_id=document.id,
                name=normalized_item["name"],
                quantity=normalized_item["quantity"],
                unit_price=normalized_item["unit_price"],
                total_price=normalized_item["total_price"],
                currency=external_item.currency or result.currency or "RON",
                selected_by_user=False,
            )

            db.add(item)
            saved_items.append(item)

        receipt_total = float(result.receipt_total or 0)

        items_total = round(
            sum(float(item.total_price or 0) for item in saved_items),
            2
        )

        total_difference = round(
            abs(items_total - receipt_total),
            2
        )

        is_valid = total_difference <= 0.05

        document.document_type = "receipt"
        document.ocr_text = "\n".join(
            f"{item.name} {item.total_price:+.2f} {item.currency}"
            for item in saved_items
        )

        external_request.provider_status = "completed"
        external_request.external_result_json = json.dumps(
            result_dict,
            ensure_ascii=False
        )
        external_request.error_message = None

        db.commit()

        for item in saved_items:
            db.refresh(item)

        duration_ms = int(
            (datetime.utcnow() - started_at).total_seconds() * 1000
        )

        return {
            "document_id": document.id,
            "case_id": document.case_id,
            "external_ocr_request_id": external_request.id,
            "provider": result.provider,
            "provider_status": external_request.provider_status,
            "duration_ms": duration_ms,
            "merchant_name": result.merchant_name,
            "items_replaced": True,
            "items_count": len(saved_items),
            "receipt_total": receipt_total,
            "items_total": items_total,
            "total_difference": total_difference,
            "is_valid": is_valid,
            "currency": result.currency or "RON",
            "provider_confidence": result.provider_confidence,
            "warnings": [] if is_valid else [
                "Azure OCR total does not match the sum of extracted items."
            ],
            "items": [
                {
                    "id": item.id,
                    "case_id": item.case_id,
                    "document_id": item.document_id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                    "currency": item.currency,
                    "selected_by_user": item.selected_by_user,
                    "created_at": item.created_at,
                }
                for item in saved_items
            ],
        }

    except Exception as error:
        external_request.provider_status = "failed"
        external_request.error_message = str(error)

        db.commit()

        raise ValueError(f"Azure Receipt OCR failed: {error}")