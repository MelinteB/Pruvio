from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.document import DocumentResponse
from app.services.case_service import get_case_by_id
from app.services.document_service import (
    get_documents,
    get_document_by_id,
    get_documents_by_case,
    save_document_bytes
)

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