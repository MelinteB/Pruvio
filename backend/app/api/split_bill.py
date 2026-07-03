from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.receipt_item import (
    ReceiptItemResponse,
    ReceiptExtractionResponse,
    SplitBillCalculationRequest,
    SplitBillCalculationResponse
)
from app.services.document_service import get_document_by_id
from app.services.case_service import get_case_by_id
from app.services.receipt_item_service import (
    extract_and_save_items_from_document,
    get_receipt_items_by_case,
    get_receipt_item_by_id,
    get_selected_items_by_case,
    select_receipt_item,
    unselect_receipt_item,
    calculate_detected_total,
    calculate_user_total
)

router = APIRouter()


@router.post(
    "/documents/{document_id}/extract-items",
    response_model=ReceiptExtractionResponse
)
def extract_receipt_items(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = get_document_by_id(db, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    try:
        result = extract_and_save_items_from_document(
            db=db,
            document=document
        )

        items = result["items"]

        return {
            "document_id": document.id,
            "case_id": document.case_id,
            "items_count": len(items),
            "detected_total": result["detected_total"],
            "receipt_total": result["receipt_total"],
            "confidence": result["confidence"],
            "warnings": result["warnings"],
            "profile_id": result["profile_id"],
            "profile_name": result["profile_name"],
            "parser_strategy": result["parser_strategy"],
            "draft_profile_created": result["draft_profile_created"],
            "draft_profile_id": result["draft_profile_id"],
            "items": items
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@router.get(
    "/cases/{case_id}/items",
    response_model=list[ReceiptItemResponse]
)
def list_case_receipt_items(
    case_id: int,
    db: Session = Depends(get_db)
):
    case = get_case_by_id(db, case_id)

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    return get_receipt_items_by_case(db, case_id)


@router.patch(
    "/items/{item_id}/select",
    response_model=ReceiptItemResponse
)
def select_item(
    item_id: int,
    db: Session = Depends(get_db)
):
    item = get_receipt_item_by_id(db, item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Receipt item not found"
        )

    return select_receipt_item(db, item)


@router.patch(
    "/items/{item_id}/unselect",
    response_model=ReceiptItemResponse
)
def unselect_item(
    item_id: int,
    db: Session = Depends(get_db)
):
    item = get_receipt_item_by_id(db, item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Receipt item not found"
        )

    return unselect_receipt_item(db, item)


@router.post(
    "/cases/{case_id}/calculate",
    response_model=SplitBillCalculationResponse
)
def calculate_split_bill_total(
    case_id: int,
    payload: SplitBillCalculationRequest,
    db: Session = Depends(get_db)
):
    case = get_case_by_id(db, case_id)

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    selected_items = get_selected_items_by_case(db, case_id)

    if not selected_items:
        raise HTTPException(
            status_code=400,
            detail="No selected items found for this case"
        )

    calculation = calculate_user_total(
        selected_items=selected_items,
        tip_percent=payload.tip_percent,
        service_charge=payload.service_charge
    )

    return {
        "case_id": case_id,
        "selected_items_count": calculation["selected_items_count"],
        "subtotal": calculation["subtotal"],
        "service_charge": calculation["service_charge"],
        "tip_percent": calculation["tip_percent"],
        "tip_amount": calculation["tip_amount"],
        "total_to_pay": calculation["total_to_pay"],
        "currency": calculation["currency"],
        "selected_items": selected_items
    }