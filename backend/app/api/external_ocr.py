from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.external_ocr import (
    ExternalOCRRequestResponse,
    ExternalOCRMockResult,
    ExternalOCRProviderUpdate,
    ExternalOCRProviderResponse
)
from app.services.external_ocr_service import (
    get_external_ocr_requests,
    get_pending_external_ocr_requests,
    get_external_ocr_request_by_id,
    process_mock_external_ocr_result,
    process_external_ocr_request_with_router,
    reset_external_ocr_request,
    get_available_external_ocr_providers,
    update_external_ocr_request_provider
)


router = APIRouter()

@router.get(
    "/providers",
    response_model=list[ExternalOCRProviderResponse]
)
def list_external_ocr_providers():
    return get_available_external_ocr_providers()

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

@router.patch(
    "/requests/{request_id}/provider",
    response_model=ExternalOCRRequestResponse
)
def set_external_ocr_request_provider(
    request_id: int,
    provider_data: ExternalOCRProviderUpdate,
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
            detail="Cannot change provider for a completed request"
        )

    return update_external_ocr_request_provider(
        db=db,
        request=request,
        provider_data=provider_data
    )

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
        "items_replaced": result["items_replaced"],
        "items_count": len(result["items"]),
        "validation": result["validation"],
        "items": result["items"]
    }

@router.post("/requests/{request_id}/process")
def process_external_ocr_request(
    request_id: int,
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

    if request.provider_status == "processing":
        raise HTTPException(
            status_code=400,
            detail="External OCR request is currently processing"
        )

    result = process_external_ocr_request_with_router(
        db=db,
        request=request
    )

    return {
        "external_ocr_request_id": result["request"].id,
        "provider_status": result["request"].provider_status,
        "provider": result["request"].preferred_provider,
        "items_replaced": result["items_replaced"],
        "items_count": len(result["items"]),
        "validation": result["validation"],
        "items": result["items"]
    }

@router.patch(
    "/requests/{request_id}/reset",
    response_model=ExternalOCRRequestResponse
)
def reset_external_ocr_request_dev(
    request_id: int,
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

    return reset_external_ocr_request(
        db=db,
        request=request
    )