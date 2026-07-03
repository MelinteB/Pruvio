from pathlib import Path

import easyocr
from pypdf import PdfReader

from app.models.document import Document


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
}

# English + Romanian-friendly Latin text.
# EasyOCR does not always need a dedicated Romanian model for basic receipts.
reader = easyocr.Reader(["en"], gpu=False)


def extract_text_from_image(file_path: str) -> str:
    image_path = Path(file_path)

    if not image_path.exists():
        raise ValueError("File does not exist")

    results = reader.readtext(str(image_path), detail=0)

    text = "\n".join(results)

    return clean_ocr_text(text)


def extract_text_from_pdf(file_path: str) -> str:
    pdf_path = Path(file_path)

    if not pdf_path.exists():
        raise ValueError("File does not exist")

    reader_pdf = PdfReader(str(pdf_path))

    text_parts = []

    for page in reader_pdf.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)

    text = "\n".join(text_parts)

    return clean_ocr_text(text)


def extract_text_from_document(document: Document) -> str:
    file_path = Path(document.path)
    extension = file_path.suffix.lower()

    if extension in IMAGE_EXTENSIONS:
        return extract_text_from_image(str(file_path))

    if extension == ".pdf":
        text = extract_text_from_pdf(str(file_path))

        if not text.strip():
            raise ValueError(
                "No text found in this PDF. Scanned PDF OCR will be added later."
            )

        return text

    raise ValueError("Unsupported file type for OCR")


def clean_ocr_text(text: str) -> str:
    lines = text.splitlines()

    cleaned_lines = []

    for line in lines:
        cleaned_line = line.strip()

        if cleaned_line:
            cleaned_lines.append(cleaned_line)

    return "\n".join(cleaned_lines)