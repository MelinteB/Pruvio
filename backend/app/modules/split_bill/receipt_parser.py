import json
import re
from dataclasses import dataclass

from app.modules.split_bill.rule_engine import (
    load_profile_rules,
    apply_profile_rules_to_ocr_text,
    apply_profile_rules_to_items
)

@dataclass
class ParsedReceipt:
    items: list[dict]
    detected_total: float
    receipt_total: float | None
    confidence: float
    warnings: list[str]


PRICE_PATTERN = re.compile(
    r"(?P<price>\d{1,6}(?:[.,]\d{2}))"
)

PRICE_AT_END_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<price>\d{1,6}(?:[.,]\d{2}))\s*(?:ron|lei|[a-z])?$",
    re.IGNORECASE
)

PRICE_ONLY_PATTERN = re.compile(
    r"^\s*(?P<price>\d{1,6}(?:[.,]\d{2}))\s*(?:ron|lei|[a-z])?\s*$",
    re.IGNORECASE
)

QUANTITY_X_UNIT_PATTERN = re.compile(
    r"^\s*\d{1,6}(?:[.,]\d{1,3})?\s+\w+\s*(?:x|×)\s*\d{1,6}(?:[.,]\d{2})\s*$",
    re.IGNORECASE
)

TOTAL_LINE_PATTERN = re.compile(
    r"\b(total|subtotal|suma|de plata|total plata|amount due|grand total)\b",
    re.IGNORECASE
)

NOISE_KEYWORDS = [
    "cui",
    "cod identificare",
    "cod fiscal",
    "s.c.",
    "srl",
    "sa",
    "str.",
    "adresa",
    "telefon",
    "tel",
    "operator",
    "casier",
    "ospatar",
    "masa",
    "bon fiscal",
    "factura",
    "nr bon",
    "nr.",
    "data",
    "ora",
    "tva",
    "vat",
    "tax",
    "card",
    "cash",
    "numerar",
    "rest",
    "change",
    "discount",
    "reducere",
    "subtotal",
    "total",
    "ecotaxa",
    "barcode",
    "cod bare",
    "voucher",
    "promotie",
    "campanie",
    "trailer",
    "tel verde",
    "multumim",
    "client",
    "iban",
    "euro",
    "bf.",
    "mg:",
    "ps:",
    "cs:",
    "tr:",
]


def normalize_price(price_text: str) -> float:
    return float(price_text.replace(",", "."))


def clean_line(line: str) -> str:
    line = line.strip()
    line = line.replace("|", " ")
    line = re.sub(r"\s+", " ", line)
    return line

def clean_item_name(name: str) -> str:
    name = clean_line(name)
    name = name.strip("-–—:;,.")

    # Remove OCR noise usually coming from currency/tax markers at the beginning.
    # Examples: "Lei COCA-COLA", "Lel COCA-COLA"
    name = re.sub(
        r"^(lei|lel|lcl|ron)\s+",
        "",
        name,
        flags=re.IGNORECASE
    )

    # Remove isolated tax/category marker at the end.
    # Example: "PROFI PUNGA MAIEU n" -> "PROFI PUNGA MAIEU"
    name = re.sub(
        r"\s+[a-zA-Z]$",
        "",
        name
    )

    # Fix OCR confusion in weight/volume fragments.
    # Examples:
    # 2OOGR -> 200GR
    # 5OOML -> 500ML
    def fix_measurement(match):
        value = match.group("value")
        unit = match.group("unit")

        fixed_value = value.replace("O", "0").replace("o", "0")
        fixed_unit = unit.upper()

        return f"{fixed_value}{fixed_unit}"

    name = re.sub(
        r"\b(?P<value>(?=[0-9Oo]*[0-9])[0-9Oo]{1,6})\s*(?P<unit>GR|G|KG|ML|L|CL|DL)\b",
        fix_measurement,
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(r"\s+", " ", name).strip()

    return name

def clean_ocr_lines(ocr_text: str) -> list[str]:
    lines = []

    for raw_line in ocr_text.splitlines():
        line = clean_line(raw_line)

        if line:
            lines.append(line)

    return lines


def is_noise_line(line: str) -> bool:
    normalized = line.lower()

    if len(normalized) < 3:
        return True

    for keyword in NOISE_KEYWORDS:
        if keyword in normalized:
            return True

    return False


def is_total_line(line: str) -> bool:
    normalized = line.lower()
    compact = re.sub(r"[^a-z0-9]", "", normalized)

    total_markers = [
        "total",
        "subtotal",
        "t0tal",
        "totai",
        "tota1",
        "sumadeplata",
        "deplata",
        "amountdue",
        "grandtotal"
    ]

    return any(marker in compact for marker in total_markers)


def is_quantity_line(line: str) -> bool:
    normalized = line.strip()

    if QUANTITY_X_UNIT_PATTERN.match(normalized):
        return True

    if " x " in normalized.lower() or "×" in normalized:
        if PRICE_PATTERN.search(normalized):
            return True

    return False


def has_letters(line: str) -> bool:
    return bool(re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", line))


def extract_last_price(line: str) -> float | None:
    matches = list(PRICE_PATTERN.finditer(line))

    if not matches:
        return None

    return normalize_price(matches[-1].group("price"))


def extract_receipt_total(lines: list[str]) -> float | None:
    possible_totals = []

    for index, line in enumerate(lines):
        if is_total_line(line):
            price = extract_last_price(line)

            if price is not None:
                possible_totals.append(price)
                continue

            # Sometimes OCR puts TOTAL on one line and amount on the next line.
            next_lines = lines[index + 1:index + 3]

            for next_line in next_lines:
                price = extract_last_price(next_line)

                if price is not None:
                    possible_totals.append(price)
                    break

    if possible_totals:
        return max(possible_totals)

    return None


def looks_like_product_name(line: str) -> bool:
    if is_noise_line(line):
        return False

    if is_quantity_line(line):
        return False

    if PRICE_ONLY_PATTERN.match(line):
        return False

    if not has_letters(line):
        return False

    return True


def remove_duplicate_items(items: list[dict]) -> list[dict]:
    """
    Removes duplicate extractions.

    If two items have the same price, and one has a weak name like "Blc",
    keep the better product name.
    """
    best_by_key = {}

    for item in items:
        price = item["total_price"]
        key = round(price, 2)

        current_best = best_by_key.get(key)

        if not current_best:
            best_by_key[key] = item
            continue

        current_score = item_name_quality_score(item["name"])
        best_score = item_name_quality_score(current_best["name"])

        if current_score > best_score:
            best_by_key[key] = item

        elif current_score == best_score:
            # If same quality and different names, keep both by making a unique key.
            unique_key = f"{key}_{item['name'].lower()}"
            best_by_key[unique_key] = item

    return list(best_by_key.values())

LOW_VALUE_ITEM_NAMES = {
    "buc",
    "blc",
    "kg",
    "gr",
    "g",
    "ml",
    "l",
    "pcs",
    "x",
    "ron",
    "lei"
}


def normalize_descriptor_name(name: str) -> str:
    cleaned = clean_item_name(name)

    if re.search(r"\d", cleaned):
        cleaned = cleaned.replace("O", "0").replace("o", "0")

    return cleaned

def is_low_value_item_name(name: str) -> bool:
    normalized = clean_item_name(name).lower()

    if normalized in LOW_VALUE_ITEM_NAMES:
        return True

    # Examples: "Blc", "Buc", "Kg"
    if len(normalized) <= 3 and normalized in LOW_VALUE_ITEM_NAMES:
        return True

    return False


def is_descriptor_name(name: str) -> bool:
    """
    Detects short descriptor fragments that usually belong to a previous product name.

    Examples:
    PET
    200GR
    500ML
    1L
    """
    normalized = normalize_descriptor_name(name).upper().replace(" ", "")

    if normalized in {"PET"}:
        return True

    if re.match(r"^\d{1,5}(GR|G|KG|ML|L)$", normalized):
        return True

    return False


def merge_product_name(pending_name: str | None, current_name: str) -> str:
    current_name = normalize_descriptor_name(current_name)

    if pending_name:
        return clean_item_name(f"{pending_name} {current_name}")

    return clean_item_name(current_name)


def item_name_quality_score(name: str) -> int:
    """
    Higher score = better product name.
    Used when two extracted items have the same price and one is probably noise.
    """
    normalized = clean_item_name(name)

    if is_low_value_item_name(normalized):
        return 0

    if is_descriptor_name(normalized):
        return 1

    score = 2

    if len(normalized) >= 6:
        score += 1

    if " " in normalized:
        score += 1

    if re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", normalized):
        score += 1

    return score

def extract_items(lines: list[str]) -> list[dict]:
    items = []
    pending_name = None

    for line in lines:
        if is_noise_line(line):
            pending_name = None
            continue

        if is_quantity_line(line):
            continue

        match = PRICE_AT_END_PATTERN.match(line)

        if match:
            raw_name = clean_item_name(match.group("name"))
            price = normalize_price(match.group("price"))

            if price <= 0:
                pending_name = None
                continue

            if is_low_value_item_name(raw_name):
                # Example: Blc 0.89
                # Usually a broken quantity/unit line, not a real product.
                pending_name = None
                continue

            if is_descriptor_name(raw_name):
                # Example:
                # COCA-COLA ZERO
                # PET 3.49
                #
                # AMANDINA
                # 2OOGR 7.49
                name = merge_product_name(pending_name, raw_name)
            else:
                # If there is a pending name and current name is very short,
                # merge them.
                if pending_name and len(raw_name) <= 6:
                    name = merge_product_name(pending_name, raw_name)
                else:
                    name = raw_name

            if name and has_letters(name):
                items.append(
                    {
                        "name": name,
                        "quantity": 1.0,
                        "unit_price": price,
                        "total_price": price,
                        "currency": "RON"
                    }
                )

            pending_name = None
            continue

        price_only = PRICE_ONLY_PATTERN.match(line)

        if price_only and pending_name:
            price = normalize_price(price_only.group("price"))

            if price > 0:
                items.append(
                    {
                        "name": pending_name,
                        "quantity": 1.0,
                        "unit_price": price,
                        "total_price": price,
                        "currency": "RON"
                    }
                )

            pending_name = None
            continue

        if looks_like_product_name(line):
            cleaned_name = clean_item_name(line)

            if is_low_value_item_name(cleaned_name):
                pending_name = None
                continue

            # Support product names split over multiple OCR lines.
            # Example:
            # COCA-COLA
            # ZERO
            # PET 3.49
            if pending_name:
                pending_name = clean_item_name(f"{pending_name} {cleaned_name}")
            else:
                pending_name = cleaned_name

    return remove_duplicate_items(items)


def validate_items_against_total(
    items: list[dict],
    receipt_total: float | None
) -> tuple[float, list[str]]:
    warnings = []

    detected_total = round(
        sum(item["total_price"] for item in items),
        2
    )

    if receipt_total is None:
        warnings.append("Receipt total was not detected.")
        return 0.60, warnings

    difference = round(
        abs(detected_total - receipt_total),
        2
    )

    if difference == 0:
        return 0.95, warnings

    if difference <= 0.50:
        warnings.append(
            f"Small mismatch between extracted items total ({detected_total}) and receipt total ({receipt_total})."
        )
        return 0.80, warnings

    warnings.append(
        f"Mismatch between extracted items total ({detected_total}) and receipt total ({receipt_total})."
    )

    return 0.45, warnings


def parse_receipt(ocr_text: str) -> ParsedReceipt:
    lines = clean_ocr_lines(ocr_text)

    receipt_total = extract_receipt_total(lines)
    items = extract_items(lines)

    detected_total = round(
        sum(item["total_price"] for item in items),
        2
    )

    confidence, warnings = validate_items_against_total(
        items=items,
        receipt_total=receipt_total
    )

    if not items:
        warnings.append("No receipt items were detected.")
        confidence = 0.20

    return ParsedReceipt(
        items=items,
        detected_total=detected_total,
        receipt_total=receipt_total,
        confidence=confidence,
        warnings=warnings
    )


def parse_receipt_with_profile(ocr_text: str, profile=None) -> dict:
    """
    Adaptive parser wrapper.

    If an active profile exists:
    - load profile rules
    - clean OCR text using profile rules
    - parse cleaned OCR text
    - clean extracted items using profile rules
    """

    rules = load_profile_rules(profile)

    profile_id = None
    profile_name = None
    parser_strategy = "generic"

    processed_ocr_text = ocr_text

    if profile:
        profile_id = profile.id
        profile_name = profile.profile_name
        parser_strategy = profile.parser_strategy

        processed_ocr_text = apply_profile_rules_to_ocr_text(
            ocr_text=ocr_text,
            rules=rules
        )

    parsed = parse_receipt(processed_ocr_text)

    items = parsed.items

    if profile:
        items = apply_profile_rules_to_items(
            items=items,
            rules=rules
        )

    detected_total = round(
        sum(item["total_price"] for item in items),
        2
    )

    confidence, warnings = validate_items_against_total(
        items=items,
        receipt_total=parsed.receipt_total
    )

    if not items:
        warnings.append("No receipt items were detected.")
        confidence = 0.20

    return {
        "items": items,
        "detected_total": detected_total,
        "receipt_total": parsed.receipt_total,
        "confidence": confidence,
        "warnings": warnings,
        "profile_id": profile_id,
        "profile_name": profile_name,
        "parser_strategy": parser_strategy
    }


def extract_items_from_ocr_text(ocr_text: str) -> list[dict]:
    parsed = parse_receipt(ocr_text)
    return parsed.items