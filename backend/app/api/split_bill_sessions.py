from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.split_bill_session import (
    SplitBillSessionCreateResponse,
    SplitBillParticipantCreate,
    SplitBillParticipantResponse,
    SplitBillSessionSelectionRequest,
    SplitBillSessionSummaryResponse
)
from app.services.split_bill_session_service import (
    create_split_bill_session,
    get_split_bill_session_by_token,
    create_split_bill_participant,
    save_participant_selection,
    get_split_bill_session_summary,
    build_share_url,
    build_qr_url
)


router = APIRouter()


@router.post(
    "/cases/{case_id}/sessions",
    response_model=SplitBillSessionCreateResponse
)
def create_session_for_case(
    case_id: int,
    db: Session = Depends(get_db)
):
    session = create_split_bill_session(
        db=db,
        case_id=case_id
    )

    return {
        "session_id": session.id,
        "case_id": session.case_id,
        "token": session.token,
        "status": session.status,
        "share_url": build_share_url(session.token),
        "qr_url": build_qr_url(session.token),
        "created_at": session.created_at,
        "expires_at": session.expires_at
    }


@router.get(
    "/sessions/{token}",
    response_model=SplitBillSessionSummaryResponse
)
def get_session_summary(
    token: str,
    db: Session = Depends(get_db)
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found"
        )

    return get_split_bill_session_summary(
        db=db,
        session=session
    )


@router.post(
    "/sessions/{token}/participants",
    response_model=SplitBillParticipantResponse
)
def create_participant(
    token: str,
    participant_data: SplitBillParticipantCreate,
    db: Session = Depends(get_db)
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found"
        )

    if not participant_data.display_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Display name is required"
        )

    return create_split_bill_participant(
        db=db,
        session=session,
        display_name=participant_data.display_name
    )


@router.post(
    "/sessions/{token}/selection",
    response_model=SplitBillSessionSummaryResponse
)
def save_selection(
    token: str,
    selection_data: SplitBillSessionSelectionRequest,
    db: Session = Depends(get_db)
):
    session = get_split_bill_session_by_token(
        db=db,
        token=token
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Split bill session not found"
        )

    try:
        return save_participant_selection(
            db=db,
            session=session,
            participant_id=selection_data.participant_id,
            selected_item_ids=selection_data.selected_item_ids
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )