from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.case import CaseCreate, CaseResponse
from app.schemas.message import MessageResponse
from app.services.case_service import (
    get_cases,
    get_case_by_id,
    create_case
)
from app.services.user_service import get_user_by_id
from app.services.message_service import get_messages_by_case

router = APIRouter()


@router.get("/", response_model=list[CaseResponse])
def list_cases(db: Session = Depends(get_db)):
    return get_cases(db)


@router.post("/", response_model=CaseResponse)
def add_case(case_data: CaseCreate, db: Session = Depends(get_db)):
    user = get_user_by_id(db, case_data.user_id)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return create_case(db, case_data)


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = get_case_by_id(db, case_id)

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    return case


@router.get("/{case_id}/messages", response_model=list[MessageResponse])
def get_case_messages(case_id: int, db: Session = Depends(get_db)):
    case = get_case_by_id(db, case_id)

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    return get_messages_by_case(db, case_id)