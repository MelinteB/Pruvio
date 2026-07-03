import re
import json


TAX_ID_PATTERNS = [
    r"RO\d{5,12}",
    r"CUI[:\s]*([A-Z]{0,2}\d{5,12})",
    r"COD IDENTIFICARE FISCALA[:\s]*([A-Z]{0,2}\d{5,12})",
]


def extract_merchant_tax_id(ocr_text: str) -> str | None:
    text = ocr_text.upper()

    for pattern in TAX_ID_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            if match.groups():
                return match.group(1)
            return match.group(0)

    return None


def extract_merchant_name(ocr_text: str) -> str | None:
    lines = [
        line.strip()
        for line in ocr_text.splitlines()
        if line.strip()
    ]

    for line in lines[:8]:
        normalized = line.upper()

        if any(marker in normalized for marker in ["S.C.", "SRL", "S.R.L", "SA", "S.A."]):
            return line.strip()

    if lines:
        return lines[0]

    return None


def detect_layout_markers(ocr_text: str) -> list[str]:
    text = ocr_text.lower()

    markers = []

    if "buc x" in text or "buc" in text:
        markers.append("contains_buc")

    if "kg x" in text or "kg" in text:
        markers.append("contains_kg")

    if "subtotal" in text:
        markers.append("contains_subtotal")

    if "total" in text:
        markers.append("contains_total")

    if "tva" in text or "vat" in text:
        markers.append("contains_tax")

    if "cash" in text or "card" in text or "numerar" in text:
        markers.append("contains_payment")

    if "bon fiscal" in text:
        markers.append("contains_fiscal_receipt")

    if "revolut.me" in text:
        markers.append("contains_revolut_link")

    return markers


def build_receipt_signature(ocr_text: str) -> dict:
    return {
        "merchant_name": extract_merchant_name(ocr_text),
        "merchant_tax_id": extract_merchant_tax_id(ocr_text),
        "layout_markers": detect_layout_markers(ocr_text)
    }


def build_receipt_signature_json(ocr_text: str) -> str:
    return json.dumps(
        build_receipt_signature(ocr_text),
        ensure_ascii=False
    )