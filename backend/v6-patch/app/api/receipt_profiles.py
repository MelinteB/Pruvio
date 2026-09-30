from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.document_service import get_document_by_id
from app.services.receipt_profile_service import (
    get_receipt_profiles,
    get_receipt_profile_by_id,
    create_receipt_profile,
    update_receipt_profile,
    activate_profile,
    save_receipt_correction
)
from app.schemas.receipt_profile import (
    ReceiptProfileCreate,
    ReceiptProfileUpdate,
    ReceiptProfileResponse,
    ReceiptCorrectionCreate,
    ReceiptCorrectionResponse
)

router = APIRouter()


@router.get("/", response_model=list[ReceiptProfileResponse])
def list_profiles(db: Session = Depends(get_db)):
    return get_receipt_profiles(db)


@router.post("/", response_model=ReceiptProfileResponse)
def add_profile(
    profile_data: ReceiptProfileCreate,
    db: Session = Depends(get_db)
):
    return create_receipt_profile(db, profile_data)

@router.patch("/{profile_id}", response_model=ReceiptProfileResponse)
def update_profile(
    profile_id: int,
    profile_data: ReceiptProfileUpdate,
    db: Session = Depends(get_db)
):
    profile = get_receipt_profile_by_id(db, profile_id)

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Receipt profile not found"
        )

    return update_receipt_profile(
        db=db,
        profile=profile,
        profile_data=profile_data
    )

@router.patch("/{profile_id}/activate", response_model=ReceiptProfileResponse)
def activate_receipt_profile(
    profile_id: int,
    db: Session = Depends(get_db)
):
    profile = get_receipt_profile_by_id(db, profile_id)

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Receipt profile not found"
        )

    return activate_profile(db, profile)


@router.post("/corrections", response_model=ReceiptCorrectionResponse)
def create_receipt_correction(
    correction_data: ReceiptCorrectionCreate,
    db: Session = Depends(get_db)
):
    document = get_document_by_id(db, correction_data.document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    return save_receipt_correction(
        db=db,
        document=document,
        correction_data=correction_data
    )