from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.modules.split_bill.receipt_parser import extract_items_from_ocr_text
from app.services.receipt_profile_service import (
    find_matching_active_profile,
    create_draft_profile_from_document,
    update_profile_success,
    update_profile_failure
)
from app.modules.split_bill.receipt_parser import parse_receipt_with_profile

from app.services.receipt_quality_service import (
    calculate_items_name_quality,
    get_extraction_decision
)
from app.services.external_ocr_service import (
    create_external_ocr_request_if_needed
)

def get_receipt_item_by_id(db: Session, item_id: int):
    return (
        db.query(ReceiptItem)
        .filter(ReceiptItem.id == item_id)
        .first()
    )


def get_receipt_items_by_case(db: Session, case_id: int):
    return (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == case_id)
        .order_by(ReceiptItem.id.asc())
        .all()
    )


def get_selected_items_by_case(db: Session, case_id: int):
    return (
        db.query(ReceiptItem)
        .filter(
            ReceiptItem.case_id == case_id,
            ReceiptItem.selected_by_user == True  # noqa: E712
        )
        .order_by(ReceiptItem.id.asc())
        .all()
    )


def get_receipt_items_by_document(db: Session, document_id: int):
    return (
        db.query(ReceiptItem)
        .filter(ReceiptItem.document_id == document_id)
        .order_by(ReceiptItem.id.asc())
        .all()
    )


def extract_and_save_items_from_document(
    db: Session,
    document: Document
):
    if not document.ocr_text:
        raise ValueError(
            "Document has no OCR text. Run OCR before extracting receipt items."
        )

    profile = find_matching_active_profile(
        db=db,
        ocr_text=document.ocr_text
    )

    parsed = parse_receipt_with_profile(
        ocr_text=document.ocr_text,
        profile=profile
    )

    parsed_items = parsed["items"]

    # Remove previous extraction for this document to avoid duplicates
    db.query(ReceiptItem).filter(
        ReceiptItem.document_id == document.id
    ).delete()

    saved_items = []

    for item in parsed_items:
        receipt_item = ReceiptItem(
            case_id=document.case_id,
            document_id=document.id,
            name=item["name"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            total_price=item["total_price"],
            currency=item["currency"],
            selected_by_user=False
        )

        db.add(receipt_item)
        saved_items.append(receipt_item)

    db.commit()

    for item in saved_items:
        db.refresh(item)

    draft_profile = None
    draft_profile_created = False

    if parsed["confidence"] < 0.70:
        draft_profile, draft_profile_created = create_draft_profile_from_document(
            db=db,
            document=document,
            parser_strategy="ai_profile_candidate_needed",
            confidence_score=parsed["confidence"]
        )

    if profile:
        if parsed["confidence"] >= 0.80:
            update_profile_success(db, profile)
        else:
            update_profile_failure(db, profile)

    name_quality = calculate_items_name_quality(saved_items)

    extraction_decision = get_extraction_decision(
        parser_confidence=parsed["confidence"],
        name_quality=name_quality,
        items_count=len(saved_items)
    )

    warnings = list(parsed["warnings"])

    if extraction_decision["external_ocr_recommended"]:
        warnings.append(
            "Local OCR result is not reliable enough. External OCR is recommended."
        )

    extraction_result = {
        "detected_total": parsed["detected_total"],
        "receipt_total": parsed["receipt_total"],
        "confidence": parsed["confidence"],
        "name_quality": name_quality,
        "external_ocr_recommended": extraction_decision["external_ocr_recommended"]
    }

    external_request, external_request_created = (
        create_external_ocr_request_if_needed(
            db=db,
            document=document,
            extraction_result=extraction_result
        )
    )
    return {
        "items": saved_items,
        "detected_total": parsed["detected_total"],
        "receipt_total": parsed["receipt_total"],
        "confidence": parsed["confidence"],
        "name_quality": name_quality,
        "external_ocr_recommended": extraction_decision["external_ocr_recommended"],
        "external_ocr_request_id": external_request.id if external_request else None,
        "external_ocr_request_created": external_request_created,
        "extraction_status": extraction_decision["extraction_status"],
        "recommended_next_step": extraction_decision["recommended_next_step"],
        "warnings": warnings,
        "profile_id": parsed["profile_id"],
        "profile_name": parsed["profile_name"],
        "parser_strategy": parsed["parser_strategy"],
        "draft_profile_created": draft_profile_created,
        "draft_profile_id": draft_profile.id if draft_profile else None
    }


def select_receipt_item(db: Session, item: ReceiptItem):
    item.selected_by_user = True
    db.commit()
    db.refresh(item)

    return item


def unselect_receipt_item(db: Session, item: ReceiptItem):
    item.selected_by_user = False
    db.commit()
    db.refresh(item)

    return item


def calculate_detected_total(items: list[ReceiptItem]) -> float:
    return round(
        sum(item.total_price for item in items),
        2
    )


def calculate_user_total(
    selected_items: list[ReceiptItem],
    tip_percent: float = 0,
    service_charge: float = 0
):
    subtotal = round(
        sum(item.total_price for item in selected_items),
        2
    )

    service_charge = round(service_charge, 2)

    tip_amount = round(
        subtotal * tip_percent / 100,
        2
    )

    total_to_pay = round(
        subtotal + service_charge + tip_amount,
        2
    )

    currency = "RON"

    if selected_items:
        currency = selected_items[0].currency

    return {
        "selected_items_count": len(selected_items),
        "subtotal": subtotal,
        "service_charge": service_charge,
        "tip_percent": tip_percent,
        "tip_amount": tip_amount,
        "total_to_pay": total_to_pay,
        "currency": currency
    }