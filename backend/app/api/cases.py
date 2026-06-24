from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.case import CaseCreate, CaseResponse
from app.services.case_service import get_cases, create_case
from app.services.user_service import get_user_by_id

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