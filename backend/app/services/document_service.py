import os
import io
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.case import Case


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_UPLOAD_ROOT = PROJECT_ROOT / "storage" / "uploads"


def upload_root() -> Path:
    configured = os.getenv("PRUVS_UPLOAD_ROOT", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("PRUVS_UPLOAD_ROOT must be an absolute directory on persistent storage.")
        return path.resolve()
    return LEGACY_UPLOAD_ROOT


def resolve_document_path(document: Document | None) -> Path | None:
    """Resolve only files inside Pruvs-managed upload directories.

    A database path must never be treated as permission to serve arbitrary
    operating-system files. This also prevents symlink escape and traversal
    through historical filenames.
    """
    if document is None or not document.case_id:
        return None
    stored = document.stored_filename or ""
    if not stored or Path(stored).name != stored or stored in (".", ".."):
        return None
    raw = str(document.path or "")
    if raw.startswith(("s3://", "local://")):
        return None

    roots = tuple(dict.fromkeys((upload_root().resolve(), LEGACY_UPLOAD_ROOT.resolve())))

    def allowed(path: Path) -> Path | None:
        candidate = path.resolve()
        # Document files must live under the case folder that owns them.
        return candidate if any(candidate.is_relative_to(base / f"case_{document.case_id}")
                                and candidate.is_file() for base in roots) else None

    if raw:
        recorded = Path(raw)
        if recorded.is_absolute():
            found = allowed(recorded)
            if found is not None:
                return found
        # Never interpret untrusted relative paths against the process CWD.

    for base in roots:
        found = allowed(base / f"case_{document.case_id}" / stored)
        if found is not None:
            return found
    return None

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
    ".webp"
}


def prepare_storage_upload(file_bytes: bytes, filename: str, mime_type: str | None) -> tuple[bytes, str, str | None]:
    """Keep a single OCR-ready copy; avoid storing the camera's oversized photo."""
    extension = Path(filename).suffix.lower()
    if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
        return file_bytes, filename, mime_type  # PDFs retain every page and embedded detail.
    try:
        with Image.open(io.BytesIO(file_bytes)) as opened:
            if opened.width * opened.height > 40_000_000:
                raise ValueError('Image is too large to process safely.')
            oriented = ImageOps.exif_transpose(opened)
            image = oriented.copy()
            # Very narrow long receipts need their native width to keep print legible.
            if min(image.size) > 1600 and max(image.size) > 3200:
                ratio = 3200 / max(image.size)
                image.thumbnail((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            if extension in {'.jpg', '.jpeg'}:
                image.convert('RGB').save(output, 'JPEG', quality=88, optimize=True, subsampling=0)
                new_extension, new_mime = '.jpg', 'image/jpeg'
            elif extension == '.webp':
                image.save(output, 'WEBP', quality=88, method=4)
                new_extension, new_mime = '.webp', 'image/webp'
            elif image.mode in ('RGB', 'L') and len(file_bytes) > 1_000_000:
                image.convert('RGB').save(output, 'JPEG', quality=90, optimize=True, subsampling=0)
                new_extension, new_mime = '.jpg', 'image/jpeg'
            else:
                image.save(output, 'PNG', optimize=True)
                new_extension, new_mime = '.png', 'image/png'
            if output.tell() < len(file_bytes) * .85:
                return output.getvalue(), str(Path(filename).with_suffix(new_extension)), new_mime
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        pass  # Leave unusual but otherwise valid images untouched for the existing OCR flow.
    return file_bytes, filename, mime_type


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

    file_bytes, original_filename, mime_type = prepare_storage_upload(file_bytes, original_filename, mime_type)
    extension = Path(original_filename).suffix.lower()

    case_folder = upload_root() / f"case_{case.id}"
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


def restore_missing_original(db: Session, case: Case, document: Document | None,
                             file_bytes: bytes, original_filename: str, mime_type: str | None) -> Document:
    """Attach an owner's replacement copy without rerunning OCR or changing extracted items."""
    if document is not None and resolve_document_path(document):
        raise ValueError("This receipt already has a downloadable original.")
    if not file_bytes or len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("Choose a nonempty file of at most 10 MB.")
    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type. Allowed: jpg, jpeg, png, webp, pdf.")
    file_bytes, original_filename, mime_type = prepare_storage_upload(file_bytes, original_filename, mime_type)
    extension = Path(original_filename).suffix.lower()
    if document is None:
        return save_document_bytes(db, case, file_bytes, original_filename, mime_type, "receipt")
    folder = upload_root() / f"case_{case.id}"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    path = folder / filename
    path.write_bytes(file_bytes)
    try:
        document.path = str(path)
        document.stored_filename = filename
        document.original_filename = original_filename
        document.mime_type = mime_type
        document.size_bytes = len(file_bytes)
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return document
