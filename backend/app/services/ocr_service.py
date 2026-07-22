from pathlib import Path

import cv2
import easyocr
import numpy as np
from pypdf import PdfReader

from app.models.document import Document
from app.modules.split_bill.receipt_parser import parse_receipt


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
}


try:
    reader = easyocr.Reader(["ro", "en"], gpu=False)
except Exception:
    reader = easyocr.Reader(["en"], gpu=False)


def clean_ocr_text(text: str) -> str:
    lines = text.splitlines()

    cleaned_lines = []

    for line in lines:
        cleaned_line = line.strip()

        if cleaned_line:
            cleaned_lines.append(cleaned_line)

    return "\n".join(cleaned_lines)


def load_image(file_path: str):
    image = cv2.imread(file_path)

    if image is None:
        raise ValueError("Could not read image file")

    return image


def resize_image(image, scale_percent: int = 180):
    height, width = image.shape[:2]

    new_width = int(width * scale_percent / 100)
    new_height = int(height * scale_percent / 100)

    return cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_CUBIC
    )


def strategy_original(image):
    return image


def strategy_gray_resized(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return resize_image(gray, 180)


def strategy_contrast_sharpen(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = resize_image(gray, 200)

    equalized = cv2.equalizeHist(resized)

    kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0]
    ])

    sharpened = cv2.filter2D(equalized, -1, kernel)

    return sharpened


def strategy_otsu_threshold(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = resize_image(gray, 220)

    blurred = cv2.GaussianBlur(resized, (3, 3), 0)

    _, thresholded = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return thresholded


def strategy_adaptive_threshold(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = resize_image(gray, 220)

    adaptive = cv2.adaptiveThreshold(
        resized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11
    )

    return adaptive


def group_easyocr_results_into_lines(results: list) -> list[str]:
    """
    Reconstructs OCR text into visual receipt lines using bounding boxes.

    This function groups tokens that are visually on the same row.
    """

    entries = []

    for result in results:
        try:
            box = result[0]
            text = result[1]
            confidence = float(result[2])
        except Exception:
            continue

        if not text or not text.strip():
            continue

        x_values = [point[0] for point in box]
        y_values = [point[1] for point in box]

        x_min = min(x_values)
        x_max = max(x_values)
        y_min = min(y_values)
        y_max = max(y_values)

        height = y_max - y_min
        y_center = (y_min + y_max) / 2

        entries.append(
            {
                "text": text.strip(),
                "confidence": confidence,
                "x_min": x_min,
                "x_max": x_max,
                "y_center": y_center,
                "height": height
            }
        )

    if not entries:
        return []

    heights = [entry["height"] for entry in entries if entry["height"] > 0]

    median_height = 12

    if heights:
        median_height = float(np.median(heights))

    row_threshold = max(6, median_height * 0.45)

    entries = sorted(
        entries,
        key=lambda entry: (entry["y_center"], entry["x_min"])
    )

    rows = []

    for entry in entries:
        added_to_row = False

        for row in rows:
            if abs(entry["y_center"] - row["y_center"]) <= row_threshold:
                row["entries"].append(entry)

                row["y_center"] = sum(
                    item["y_center"]
                    for item in row["entries"]
                ) / len(row["entries"])

                added_to_row = True
                break

        if not added_to_row:
            rows.append(
                {
                    "y_center": entry["y_center"],
                    "entries": [entry]
                }
            )

    rows = sorted(rows, key=lambda row: row["y_center"])

    lines = []

    for row in rows:
        row_entries = sorted(
            row["entries"],
            key=lambda entry: entry["x_min"]
        )

        line = " ".join(
            entry["text"]
            for entry in row_entries
        )

        line = clean_ocr_text(line)

        if line:
            lines.append(line)

    return lines


def run_easyocr(image) -> dict:
    results = reader.readtext(
        image,
        detail=1,
        paragraph=False
    )

    confidences = []

    for result in results:
        try:
            confidence = float(result[2])
            confidences.append(confidence)
        except Exception:
            continue

    lines = group_easyocr_results_into_lines(results)

    average_confidence = 0.0

    if confidences:
        average_confidence = sum(confidences) / len(confidences)

    return {
        "text": clean_ocr_text("\n".join(lines)),
        "average_confidence": average_confidence
    }


def score_item_name(name: str) -> float:
    cleaned = name.strip()

    if not cleaned:
        return 0

    score = 0

    letters = sum(character.isalpha() for character in cleaned)
    digits = sum(character.isdigit() for character in cleaned)
    spaces = cleaned.count(" ")

    if letters >= 3:
        score += 2

    if len(cleaned) >= 6:
        score += 1

    if spaces >= 1:
        score += 1

    if digits > 0:
        score += 0.5

    if cleaned.startswith("~"):
        score -= 2

    strange_chars = sum(
        not character.isalnum()
        and character not in [" ", "-", "/", "."]
        for character in cleaned
    )

    if strange_chars > 0:
        score -= strange_chars

    return score


def score_ocr_candidate(
    ocr_text: str,
    average_confidence: float
) -> dict:
    parsed = parse_receipt(ocr_text)

    score = 0.0

    score += average_confidence * 100
    score += parsed.confidence * 100
    score += len(parsed.items) * 5

    if parsed.receipt_total is not None:
        score += 20

    if parsed.receipt_total is not None:
        difference = abs(parsed.detected_total - parsed.receipt_total)

        if difference == 0:
            score += 80
        elif difference <= 0.50:
            score += 30
        else:
            score -= 80

        # Strong penalty if detected total is much smaller than receipt total.
        # Example: items total 8.65 but receipt total wrongly detected as CASH 50.00.
        if parsed.detected_total > 0 and parsed.receipt_total > parsed.detected_total * 2:
            score -= 100

    if parsed.items:
        name_scores = [
            score_item_name(item["name"])
            for item in parsed.items
        ]

        score += sum(name_scores)

    return {
        "score": round(score, 2),
        "items_count": len(parsed.items),
        "detected_total": parsed.detected_total,
        "receipt_total": parsed.receipt_total,
        "parser_confidence": parsed.confidence,
        "warnings": parsed.warnings
    }


def extract_ocr_candidates_from_image(file_path: str) -> list[dict]:
    image = load_image(file_path)

    strategies = [
        ("original", strategy_original),
        ("gray_resized", strategy_gray_resized),
        ("contrast_sharpen", strategy_contrast_sharpen),
        ("otsu_threshold", strategy_otsu_threshold),
        ("adaptive_threshold", strategy_adaptive_threshold)
    ]

    candidates = []

    for strategy_name, strategy_function in strategies:
        try:
            processed_image = strategy_function(image)

            ocr_result = run_easyocr(processed_image)

            candidate_score = score_ocr_candidate(
                ocr_text=ocr_result["text"],
                average_confidence=ocr_result["average_confidence"]
            )

            candidates.append(
                {
                    "strategy": strategy_name,
                    "ocr_text": ocr_result["text"],
                    "average_confidence": round(
                        ocr_result["average_confidence"],
                        4
                    ),
                    **candidate_score
                }
            )

        except Exception as error:
            candidates.append(
                {
                    "strategy": strategy_name,
                    "ocr_text": "",
                    "average_confidence": 0.0,
                    "score": 0.0,
                    "items_count": 0,
                    "detected_total": 0.0,
                    "receipt_total": None,
                    "parser_confidence": 0.0,
                    "warnings": [str(error)]
                }
            )

    candidates = sorted(
        candidates,
        key=lambda candidate: candidate["score"],
        reverse=True
    )

    return candidates


def extract_text_from_image(file_path: str) -> str:
    image_path = Path(file_path)

    if not image_path.exists():
        raise ValueError("File does not exist")

    candidates = extract_ocr_candidates_from_image(str(image_path))

    if not candidates:
        raise ValueError("OCR failed. No candidates generated.")

    best_candidate = candidates[0]

    return best_candidate["ocr_text"]


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


def extract_ocr_candidates_from_document(document: Document) -> list[dict]:
    file_path = Path(document.path)
    extension = file_path.suffix.lower()

    if extension not in IMAGE_EXTENSIONS:
        raise ValueError("OCR candidates are only available for images.")

    return extract_ocr_candidates_from_image(str(file_path))