import re


BAD_NAME_PATTERNS = [
    r"^[~\-_]+",
    r"\bx\s+\d+[.,]\d{2}",
    r"runku",
    r"jio",
    r"wua",
    r"odu",
    r"mivta",
    r"uly",
    r"\b0\s+\d+kg\b",
    r"[^\w\s\-\/\.,]",
]


def score_product_name(name: str) -> float:
    cleaned = name.strip()

    if not cleaned:
        return 0.0

    score = 1.0

    letters = sum(char.isalpha() for char in cleaned)
    digits = sum(char.isdigit() for char in cleaned)
    spaces = cleaned.count(" ")

    if letters < 3:
        score -= 0.5

    if len(cleaned) < 4:
        score -= 0.4

    if digits > letters:
        score -= 0.4

    if spaces >= 1:
        score += 0.1

    for pattern in BAD_NAME_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            score -= 0.35

    strange_chars = sum(
        not char.isalnum()
        and char not in [" ", "-", "/", ".", ","]
        for char in cleaned
    )

    score -= strange_chars * 0.1

    return max(0.0, min(score, 1.0))


def calculate_items_name_quality(items: list) -> float:
    if not items:
        return 0.0

    scores = []

    for item in items:
        name = item.name if hasattr(item, "name") else item.get("name", "")
        scores.append(score_product_name(name))

    return round(sum(scores) / len(scores), 2)


def should_use_external_ocr(
    parser_confidence: float,
    name_quality: float,
    items_count: int
) -> bool:
    if items_count == 0:
        return True

    if parser_confidence < 0.80:
        return True

    if name_quality < 0.70:
        return True

    return False


def get_extraction_decision(
    parser_confidence: float,
    name_quality: float,
    items_count: int
) -> dict:
    external_needed = should_use_external_ocr(
        parser_confidence=parser_confidence,
        name_quality=name_quality,
        items_count=items_count
    )

    if external_needed:
        return {
            "external_ocr_recommended": True,
            "extraction_status": "needs_external_ocr",
            "recommended_next_step": (
                "Local OCR result is weak. Try external receipt OCR provider "
                "before allowing split bill."
            )
        }

    return {
        "external_ocr_recommended": False,
        "extraction_status": "ready_for_split",
        "recommended_next_step": (
            "Extraction is reliable enough for item selection and split calculation."
        )
    }