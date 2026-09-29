from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.standalone_app_service import (
    create_standalone_receipt_case,
    get_receipt_view,
    list_recent_receipts,
)


router = APIRouter()


@router.get("/receipts")
def recent_receipts(
    limit: int = 8,
    db: Session = Depends(get_db),
):
    return list_recent_receipts(db, limit=max(1, min(limit, 50)))


@router.get("/receipts/{case_id}")
def receipt_detail(
    case_id: int,
    db: Session = Depends(get_db),
):
    receipt = get_receipt_view(db, case_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return receipt


@router.post("/receipts/upload")
async def upload_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        file_bytes = await file.read()
        result = create_standalone_receipt_case(
            db=db,
            file_bytes=file_bytes,
            original_filename=file.filename or "receipt.jpg",
            mime_type=file.content_type,
        )
        case_id = result["case"].id
        receipt = get_receipt_view(db, case_id)
        return {
            "status": "processed",
            "case_id": case_id,
            "receipt_url": f"/receipt/{case_id}",
            "receipt": receipt,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Receipt processing failed: {error}")
