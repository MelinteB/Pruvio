from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.browser_upload_token_service import verify_browser_upload_token
from app.services.document_service import MAX_FILE_SIZE_BYTES
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

@router.post("/receipts/browser-upload")
async def browser_upload_receipt(
    file: UploadFile = File(...),
    x_pruvs_upload_token: str | None = Header(
        default=None,
        alias="X-Pruvs-Upload-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Upload a receipt directly from the browser over HTTP multipart/form-data.

    v6.8 uses this endpoint for cropped images and PDFs so large image/base64
    payloads never travel through NiceGUI's WebSocket transport. The signed,
    short-lived token binds the upload to the currently signed-in Pruvs user.
    """
    try:
        user_id = verify_browser_upload_token(x_pruvs_upload_token or "")

        # Read one byte beyond the configured limit so oversized uploads are
        # rejected without loading an arbitrarily large request into memory.
        file_bytes = await file.read(MAX_FILE_SIZE_BYTES + 1)
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValueError("File is too large. Maximum size is 10 MB.")

        result = create_standalone_receipt_case(
            db=db,
            file_bytes=file_bytes,
            original_filename=file.filename or "receipt.jpg",
            mime_type=file.content_type,
            user_id=user_id,
        )
        case_id = result["case"].id
        ocr = result.get("ocr") or {}
        return {
            "status": "processed",
            "case_id": case_id,
            "receipt_url": f"/receipt/{case_id}",
            "fallback_used": bool(ocr.get("fallback_used")),
            "provider": ocr.get("provider") or ocr.get("primary_provider"),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Receipt processing failed: {error}")

