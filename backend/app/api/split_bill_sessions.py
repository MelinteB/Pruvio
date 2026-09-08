import io

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.receipt_item import ReceiptItem
from app.schemas.split_bill_session import (
    SplitBillSessionCreateRequest,
    SplitBillSessionCreateResponse,
    SplitBillJoinRequest,
    SplitBillJoinResponse,
    SplitBillSessionSelectionRequest,
    SplitBillSessionCloseRequest,
    SplitBillSessionSummaryResponse,
    SplitBillCloseResponse,
)
from app.services.split_bill_session_service import (
    create_split_bill_session,
    get_split_bill_session_by_token,
    get_split_bill_session_summary,
    join_split_bill_session,
    save_participant_selection,
    close_split_bill_session,
    build_share_url,
    build_qr_url,
    build_widget_url,
    get_owner_participant,
)


router = APIRouter()


@router.get("/s/{token}")
def short_split_bill_link(token: str):
    return RedirectResponse(
        url=f"/split-bill/sessions/{token}/join",
        status_code=302,
    )


@router.get("/cases/{case_id}/debug-items")
def debug_case_receipt_items(
    case_id: int,
    db: Session = Depends(get_db),
):
    """
    Temporary debug endpoint.

    Use this to confirm that the split-bill API can see the receipt_items
    saved by the Azure OCR endpoint for the same case_id.
    Remove this endpoint before production release.
    """

    items = (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == case_id)
        .order_by(ReceiptItem.id.asc())
        .all()
    )

    total_receipt_items = db.query(ReceiptItem).count()

    return {
        "case_id": case_id,
        "items_count_for_case": len(items),
        "total_receipt_items_visible": total_receipt_items,
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
            for item in items
        ],
    }


@router.post(
    "/cases/{case_id}/sessions",
    response_model=SplitBillSessionCreateResponse,
)
def create_session_for_case(
    case_id: int,
    session_data: SplitBillSessionCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        session = create_split_bill_session(
            db=db,
            case_id=case_id,
            owner_user_id=session_data.owner_user_id,
            expected_participants_count=session_data.expected_participants_count,
        )

        summary = get_split_bill_session_summary(
            db=db,
            session=session,
        )

        owner_participant = get_owner_participant(
            db=db,
            session=session,
        )

        owner_widget_url = None

        if owner_participant:
            owner_widget_url = build_widget_url(
                token=session.token,
                participant_id=owner_participant.id,
            )

        return {
            "session_id": session.id,
            "case_id": session.case_id,
            "owner_user_id": session.owner_user_id,
            "token": session.token,
            "status": session.status,
            "expected_participants_count": session.expected_participants_count,
            "joined_participants_count": summary["joined_participants_count"],
            "missing_participants_count": summary["missing_participants_count"],
            "can_close": summary["can_close"],
            "close_block_reason": summary["close_block_reason"],
            "share_url": build_share_url(session.token),
            "qr_url": build_qr_url(session.token),
            "owner_widget_url": owner_widget_url,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get(
    "/sessions/{token}",
    response_model=SplitBillSessionSummaryResponse,
)
def get_session_summary(
    token: str,
    db: Session = Depends(get_db),
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token,
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found.",
        )

    return get_split_bill_session_summary(
        db=db,
        session=session,
    )


@router.post(
    "/sessions/{token}/join",
    response_model=SplitBillJoinResponse,
)
def join_session(
    token: str,
    join_data: SplitBillJoinRequest,
    db: Session = Depends(get_db),
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token,
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found.",
        )

    try:
        return join_split_bill_session(
            db=db,
            session=session,
            phone_number=join_data.phone_number,
            display_name=join_data.display_name,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.post(
    "/sessions/{token}/selection",
    response_model=SplitBillSessionSummaryResponse,
)
def save_selection(
    token: str,
    selection_data: SplitBillSessionSelectionRequest,
    db: Session = Depends(get_db),
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token,
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found.",
        )

    try:
        return save_participant_selection(
            db=db,
            session=session,
            participant_id=selection_data.participant_id,
            selected_item_ids=selection_data.selected_item_ids,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.post(
    "/sessions/{token}/close",
    response_model=SplitBillCloseResponse,
)
def close_session(
    token: str,
    close_data: SplitBillSessionCloseRequest,
    db: Session = Depends(get_db),
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token,
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found.",
        )

    try:
        return close_split_bill_session(
            db=db,
            session=session,
            owner_user_id=close_data.owner_user_id,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/sessions/{token}/qr")
def get_session_qr(
    token: str,
    db: Session = Depends(get_db),
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token,
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found.",
        )

    share_url = build_share_url(session.token)

    qr_image = qrcode.make(share_url)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    buffer.seek(0)

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
    )
