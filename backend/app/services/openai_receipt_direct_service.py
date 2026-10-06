import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.services.azure_receipt_direct_service import (
    MONEY_TOLERANCE,
    _validation_status,
    apply_basket_adjustments_proportionally,
    build_receipt_structure,
    finalize_receipt_items,
    model_to_dict,
)
from app.services.ocr_providers.openai_receipt_provider import OpenAIReceiptOCRProvider
from app.services.receipt_translation_service import translate_receipt_item_names


def _retag_openai_adjustment_sources(structure: dict) -> None:
    """Keep audit metadata provider-neutral when Azure normalization is reused."""
    for key in ("applied_adjustments", "basket_adjustments", "unresolved_adjustments"):
        for adjustment in structure.get(key, []):
            if adjustment.get("source") == "azure_structured":
                adjustment["source"] = "openai_structured"

    for item in structure.get("items", []):
        for adjustment in item.get("applied_adjustments", []):
            if adjustment.get("source") == "azure_structured":
                adjustment["source"] = "openai_structured"


def process_document_with_openai_receipt_direct(
    db: Session,
    document_id: int,
    reason: str = "azure_receipt_ocr_fallback",
    *,
    fallback_used: bool = True,
) -> dict:
    """Persist OpenAI receipt extraction using Pruvs' existing receipt models."""

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise ValueError("Document not found.")
    if not document.case_id:
        raise ValueError("Document is not linked to a case.")

    provider = OpenAIReceiptOCRProvider()
    if not provider.is_configured():
        raise ValueError(
            "OpenAI receipt fallback is not configured. "
            "Check OPENAI_API_KEY and OPENAI_RECEIPT_MODEL."
        )

    external_request = ExternalOCRRequest(
        document_id=document.id,
        case_id=document.case_id,
        reason=reason,
        provider_status="processing",
        preferred_provider="openai_receipt",
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
        result = provider.process_document(document=document, request=external_request)
        result_dict = model_to_dict(result)
        result_dict["_openai_usage"] = provider.last_usage

        existing_item_ids = [
            item_id
            for item_id, in db.query(ReceiptItem.id)
            .filter(ReceiptItem.document_id == document.id)
            .all()
        ]
        if existing_item_ids:
            db.query(SplitBillItemAssignment).filter(
                SplitBillItemAssignment.receipt_item_id.in_(existing_item_ids)
            ).delete(synchronize_session=False)

        db.query(ReceiptItem).filter(
            ReceiptItem.document_id == document.id
        ).delete(synchronize_session=False)

        # Reuse the same normalization and reconciliation path as Azure.
        # OpenAI already receives instructions to return purchased lines only,
        # but these helpers safely handle any explicit adjustment lines too.
        structure = build_receipt_structure(
            raw_items=result.items,
            default_currency=result.currency or "RON",
        )
        _retag_openai_adjustment_sources(structure)
        apply_basket_adjustments_proportionally(structure=structure)
        net_items = finalize_receipt_items(structure=structure)

        translation = translate_receipt_item_names(
            [net_item["name"] for net_item in net_items]
        )
        if translation.error:
            print(f"Receipt translation skipped: {translation.error}")

        saved_items = []
        for net_item in net_items:
            item = ReceiptItem(
                case_id=document.case_id,
                document_id=document.id,
                name=net_item["name"],
                translated_name=translation.translated_names.get(net_item["name"]),
                source_language=translation.source_language,
                quantity=net_item["quantity"],
                unit_price=net_item["unit_price"],
                total_price=net_item["total_price"],
                currency=net_item["currency"],
                selected_by_user=False,
            )
            db.add(item)
            saved_items.append(item)

        receipt_total = round(float(result.receipt_total or 0), 2)
        items_total = round(
            sum(float(item.total_price or 0) for item in saved_items),
            2,
        )
        signed_difference = round(items_total - receipt_total, 2)
        total_difference = round(abs(signed_difference), 2)
        is_valid = total_difference <= MONEY_TOLERANCE
        validation_status = _validation_status(
            items_total=items_total,
            receipt_total=receipt_total,
            unresolved_adjustments=structure["unresolved_adjustments"],
        )

        warnings = []
        if not is_valid:
            warnings.append(
                "OpenAI OCR total does not match the sum of resolved items. "
                "Pruvs did not invent a missing discount or charge."
            )
        if structure["unresolved_adjustments"]:
            warnings.append(
                f"{len(structure['unresolved_adjustments'])} adjustment(s) "
                "could not be associated safely."
            )

        document.document_type = "receipt"
        document.ocr_text = "\n".join(
            f"{item.name} {item.total_price:+.2f} {item.currency}"
            for item in saved_items
        )

        audit_payload = {
            "provider_result": result_dict,
            "openai_usage": provider.last_usage,
            "adjustments": {
                "applied": structure["applied_adjustments"],
                "basket": structure["basket_adjustments"],
                "unresolved": structure["unresolved_adjustments"],
            },
            "validation": {
                "receipt_total": receipt_total,
                "items_total": items_total,
                "signed_difference": signed_difference,
                "status": validation_status,
            },
        }

        external_request.provider_status = "completed"
        external_request.external_result_json = json.dumps(
            audit_payload,
            ensure_ascii=False,
            default=str,
        )
        external_request.error_message = None
        db.commit()

        for item in saved_items:
            db.refresh(item)

        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)

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
            "signed_difference": signed_difference,
            "total_difference": total_difference,
            "is_valid": is_valid,
            "validation_status": validation_status,
            "currency": result.currency or "RON",
            "provider_confidence": result.provider_confidence,
            "fallback_used": bool(fallback_used),
            "openai_usage": provider.last_usage,
            "warnings": warnings,
            "adjustments": {
                "applied": structure["applied_adjustments"],
                "basket": structure["basket_adjustments"],
                "unresolved": structure["unresolved_adjustments"],
            },
            "items": [
                {
                    "id": item.id,
                    "case_id": item.case_id,
                    "document_id": item.document_id,
                    "name": item.name,
                    "translated_name": item.translated_name,
                    "source_language": item.source_language,
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
        raise ValueError(f"OpenAI Receipt OCR fallback failed: {error}") from error
