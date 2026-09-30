from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.case import Case


PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_ROOT = PROJECT_ROOT / "storage" / "uploads"

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
    ".webp"
}


def get_documents(db: Session):
    return (
        db.query(Document)
        .order_by(Document.created_at.desc())
        .all()
    )


def get_document_by_id(db: Session, document_id: int):
    return (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )


def get_documents_by_case(db: Session, case_id: int):
    return (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.created_at.asc())
        .all()
    )


def save_document_bytes(
    db: Session,
    case: Case,
    file_bytes: bytes,
    original_filename: str,
    mime_type: str | None,
    document_type: str = "unknown"
):
    if not file_bytes:
        raise ValueError("Empty file")

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("File is too large. Maximum size is 10 MB.")

    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Unsupported file type. Allowed: jpg, jpeg, png, webp, pdf."
        )

    case_folder = UPLOAD_ROOT / f"case_{case.id}"
    case_folder.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4().hex}{extension}"
    stored_path = case_folder / stored_filename

    stored_path.write_bytes(file_bytes)

    document = Document(
        case_id=case.id,
        document_type=document_type,
        original_filename=original_filename,
        stored_filename=stored_filename,
        path=str(stored_path),
        mime_type=mime_type,
        size_bytes=len(file_bytes),
        ocr_text=None
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document