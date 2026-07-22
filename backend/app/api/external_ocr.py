from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.external_ocr import (
    ExternalOCRRequestResponse,
    ExternalOCRMockResult
)
from app.services.external_ocr_service import (
    get_external_ocr_requests,
    get_pending_external_ocr_requests,
    get_external_ocr_request_by_id,
    process_mock_external_ocr_result
)


router = APIRouter()


@router.get(
    "/requests",
    response_model=list[ExternalOCRRequestResponse]
)
def list_external_ocr_requests(
    db: Session = Depends(get_db)
):
    return get_external_ocr_requests(db)


@router.get(
    "/requests/pending",
    response_model=list[ExternalOCRRequestResponse]
)
def list_pending_external_ocr_requests(
    db: Session = Depends(get_db)
):
    return get_pending_external_ocr_requests(db)


@router.get(
    "/requests/{request_id}",
    response_model=ExternalOCRRequestResponse
)
def get_external_ocr_request(
    request_id: int,
    db: Session = Depends(get_db)
):
    request = get_external_ocr_request_by_id(db, request_id)

    if not request:
        raise HTTPException(
            status_code=404,
            detail="External OCR request not found"
        )

    return request

@router.post("/requests/{request_id}/process-mock")
def process_external_ocr_request_with_mock(
    request_id: int,
    mock_result: ExternalOCRMockResult,
    db: Session = Depends(get_db)
):
    request = get_external_ocr_request_by_id(
        db=db,
        request_id=request_id
    )

    if not request:
        raise HTTPException(
            status_code=404,
            detail="External OCR request not found"
        )

    if request.provider_status == "completed":
        raise HTTPException(
            status_code=400,
            detail="External OCR request is already completed"
        )

    result = process_mock_external_ocr_result(
        db=db,
        request=request,
        mock_result=mock_result
    )

    return {
        "external_ocr_request_id": result["request"].id,
        "provider_status": result["request"].provider_status,
        "provider": result["request"].preferred_provider,
        "items_replaced": len(result["items"]),
        "items": result["items"]
    }