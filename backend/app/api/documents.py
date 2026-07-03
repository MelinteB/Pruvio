from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.schemas.document import (
    DocumentResponse,
    DocumentClassificationResponse,
    TextClassificationRequest,
    DocumentOCRResponse
)
from app.services.case_service import get_case_by_id
from app.services.document_service import (
    get_documents,
    get_document_by_id,
    get_documents_by_case,
    save_document_bytes
)
from app.services.document_classifier import (
    classify_document,
    classify_document_from_text
)
from app.services.case_service import update_case_module
from app.services.ocr_service import extract_text_from_document

router = APIRouter()


@router.get("/", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    return get_documents(db)


@router.get("/case/{case_id}", response_model=list[DocumentResponse])
def list_documents_for_case(
    case_id: int,
    db: Session = Depends(get_db)
):
    case = get_case_by_id(db, case_id)

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    return get_documents_by_case(db, case_id)

@router.post("/classify-text")
def classify_text(
    payload: TextClassificationRequest
):
    result = classify_document_from_text(payload.text)

    return result

@router.post("/{document_id}/classify", response_model=DocumentClassificationResponse)
def classify_uploaded_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = get_document_by_id(db, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    result = classify_document(document)

    document.document_type = result["document_type"]

    case = get_case_by_id(db, document.case_id)

    if case and result["suggested_module"] != "unknown":
        update_case_module(
            db=db,
            case=case,
            module=result["suggested_module"]
        )

    db.commit()
    db.refresh(document)

    return {
        "document_id": document.id,
        "document_type": result["document_type"],
        "suggested_module": result["suggested_module"],
        "confidence": result["confidence"],
        "reason": result["reason"]
    }

@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    document = get_document_by_id(db, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    return document

@router.post("/{document_id}/ocr", response_model=DocumentOCRResponse)
def run_ocr_on_document(
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
        ocr_text = extract_text_from_document(document)

        document.ocr_text = ocr_text
        db.commit()
        db.refresh(document)

        classification = classify_document(document)

        document.document_type = classification["document_type"]

        case = get_case_by_id(db, document.case_id)

        if case and classification["suggested_module"] != "unknown":
            update_case_module(
                db=db,
                case=case,
                module=classification["suggested_module"]
            )

        db.commit()
        db.refresh(document)

        return {
            "document_id": document.id,
            "ocr_text": document.ocr_text,
            "classification": classification
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"OCR failed: {str(error)}"
        )
    
@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    case_id: int = Form(...),
    document_type: str = Form("unknown"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    case = get_case_by_id(db, case_id)

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found"
        )

    try:
        file_bytes = await file.read()

        document = save_document_bytes(
            db=db,
            case=case,
            file_bytes=file_bytes,
            original_filename=file.filename or "uploaded_file",
            mime_type=file.content_type,
            document_type=document_type
        )

        return document

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )