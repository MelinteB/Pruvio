import json
import re
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.services.ocr_providers.azure_receipt_provider import AzureReceiptOCRProvider


MONEY_TOLERANCE = 0.05

LINE_DISCOUNT_KEYWORDS = [
    "reducere",
    "reduceri",
    "discount",
    "promo",
    "promotie",
    "promotion",
    "rabatt",
]

BASKET_DISCOUNT_KEYWORDS = [
    "voucher",
    "coupon",
    "cupon",
    "cod promo",
    "promo code",
    "discount total",
    "reducere totala",
    "reducere total",
    "loyalty",
    "fidelitate",
]

SURCHARGE_KEYWORDS = [
    "service charge",
    "taxa serviciu",
    "serviciu",
    "bacsis",
    "tip",
    "ambalaj",
    "packaging",
    "deposit",
    "garantie",
]


def model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")

    if hasattr(model, "dict"):
        return model.dict()

    return model


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace("ă", "a")
        .replace("â", "a")
        .replace("î", "i")
        .replace("ș", "s")
        .replace("ş", "s")
        .replace("ț", "t")
        .replace("ţ", "t")
    )


def safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except Exception:
        return default


def parse_money_from_text(text: str | None) -> float | None:
    """
    Extract the last money-like number from a raw OCR line.

    Examples:
        "REDUCERE 21,41" -> 21.41
        "Discount - 5.00 RON" -> -5.00
    """
    if not text:
        return None

    matches = re.findall(r"[-+]?\s*\d+(?:[.,]\d{1,2})?", str(text))

    if not matches:
        return None

    candidate = matches[-1].replace(" ", "").replace(",", ".")

    try:
        return float(candidate)
    except ValueError:
        return None


def classify_receipt_line(
    name: str | None,
    total_price: float | None = None,
    unit_price: float | None = None,
) -> str:
    """
    Classify a structured/raw receipt line without assuming that every
    adjustment belongs to the previous item.

    Returns:
        product
        line_discount
        basket_discount
        surcharge
        unknown_adjustment
    """
    normalized = normalize_text(name)

    if any(keyword in normalized for keyword in BASKET_DISCOUNT_KEYWORDS):
        return "basket_discount"

    if any(keyword in normalized for keyword in SURCHARGE_KEYWORDS):
        return "surcharge"

    if any(keyword in normalized for keyword in LINE_DISCOUNT_KEYWORDS):
        return "line_discount"

    # Tolerate common OCR truncation: REDUCERE -> REDUCER / REDUC.
    if normalized.startswith("reduc"):
        return "line_discount"

    numeric_total = safe_float(total_price, 0.0)
    numeric_unit = (
        safe_float(unit_price, 0.0)
        if unit_price is not None
        else None
    )

    # A negative amount with no descriptive keyword is an adjustment,
    # but we do not guess whether it is item-level or basket-level.
    if numeric_total < 0 or (
        numeric_unit is not None and numeric_unit < 0
    ):
        return "unknown_adjustment"

    return "product"


def adjustment_amount(
    total_price: float | None,
    unit_price: float | None,
    adjustment_type: str,
) -> float:
    """
    Normalize an adjustment sign:
      discounts -> negative
      surcharges -> positive
    """
    source = safe_float(total_price, 0.0)

    if source == 0 and unit_price is not None:
        source = safe_float(unit_price, 0.0)

    if adjustment_type in {
        "line_discount",
        "basket_discount",
        "unknown_adjustment",
    }:
        return -abs(source)

    if adjustment_type == "surcharge":
        return abs(source)

    return source


def can_attach_line_adjustment(
    item: dict | None,
    amount: float,
) -> bool:
    """
    Only attach a line-level discount when it is financially plausible.

    We still require explicit line-discount evidence elsewhere; this function
    is only the numeric safety check.
    """
    if not item:
        return False

    original_total = abs(
        safe_float(item.get("original_total_price"), 0.0)
    )

    if original_total <= 0:
        return False

    discount = abs(amount)

    if discount <= MONEY_TOLERANCE:
        return False

    # A line discount should not make the product negative.
    if discount > original_total + MONEY_TOLERANCE:
        return False

    return True


def _format_item_name(item: dict) -> str:
    parts = [item["base_name"]]
    currency = item.get("currency") or "RON"

    line_adjustment = round(
        safe_float(item.get("line_adjustment_total"), 0.0),
        2
    )

    basket_adjustment = round(
        safe_float(item.get("basket_adjustment_total"), 0.0),
        2
    )

    if abs(line_adjustment) > MONEY_TOLERANCE:
        label = "Reducere" if line_adjustment < 0 else "Ajustare"
        parts.append(
            f"{label} {line_adjustment:+.2f} {currency}"
        )

    if abs(basket_adjustment) > MONEY_TOLERANCE:
        label = (
            "Ajustare bon"
            if basket_adjustment < 0
            else "Taxa/Ajustare bon"
        )
        parts.append(
            f"{label} {basket_adjustment:+.2f} {currency}"
        )

    return " | ".join(parts)


def _apply_adjustment_to_item(
    item: dict,
    amount: float,
    *,
    source_name: str,
    source: str,
) -> None:
    item["line_adjustment_total"] = round(
        safe_float(item.get("line_adjustment_total"), 0.0)
        + amount,
        2,
    )

    item["total_price"] = round(
        safe_float(item.get("total_price"), 0.0)
        + amount,
        2,
    )

    quantity = safe_float(item.get("quantity"), 1.0)

    if quantity:
        item["unit_price"] = round(
            item["total_price"] / quantity,
            2,
        )

    item.setdefault("applied_adjustments", []).append(
        {
            "type": "line_discount" if amount < 0 else "line_adjustment",
            "name": source_name,
            "amount": round(amount, 2),
            "source": source,
        }
    )


def build_receipt_structure(
    raw_items: list,
    default_currency: str = "RON",
) -> dict:
    """
    Build split-bill friendly products while preserving adjustment semantics.

    Rules:
    - Explicit item-level discounts may be attached to the previous product.
    - Explicit voucher/coupon/global discounts are kept as basket adjustments.
    - Surcharges/tips/service charges are basket adjustments.
    - Unlabelled negative values are not guessed; they remain unresolved.
    """
    items: list[dict] = []
    basket_adjustments: list[dict] = []
    unresolved_adjustments: list[dict] = []
    applied_adjustments: list[dict] = []

    last_product_index: int | None = None

    for raw_item in raw_items:
        name = raw_item.name or "Unknown item"
        currency = raw_item.currency or default_currency or "RON"
        quantity = safe_float(raw_item.quantity, 1.0)
        unit_price = (
            safe_float(raw_item.unit_price)
            if raw_item.unit_price is not None
            else None
        )
        total_price = safe_float(raw_item.total_price, 0.0)

        line_type = classify_receipt_line(
            name=name,
            total_price=total_price,
            unit_price=unit_price,
        )

        if line_type == "product":
            items.append(
                {
                    "base_name": name,
                    "name": name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "original_total_price": total_price,
                    "total_price": total_price,
                    "currency": currency,
                    "line_adjustment_total": 0.0,
                    "basket_adjustment_total": 0.0,
                    "applied_adjustments": [],
                }
            )
            last_product_index = len(items) - 1
            continue

        amount = adjustment_amount(
            total_price=total_price,
            unit_price=unit_price,
            adjustment_type=line_type,
        )

        if line_type == "line_discount":
            previous_item = (
                items[last_product_index]
                if last_product_index is not None
                else None
            )

            if can_attach_line_adjustment(previous_item, amount):
                _apply_adjustment_to_item(
                    previous_item,
                    amount,
                    source_name=name,
                    source="azure_structured",
                )

                applied_adjustments.append(
                    {
                        "type": "line_discount",
                        "name": name,
                        "amount": round(amount, 2),
                        "target_item": previous_item["base_name"],
                        "source": "azure_structured",
                    }
                )
            else:
                unresolved_adjustments.append(
                    {
                        "type": "line_discount",
                        "name": name,
                        "amount": round(amount, 2),
                        "reason": "No safe product association found.",
                        "source": "azure_structured",
                    }
                )

            continue

        if line_type in {"basket_discount", "surcharge"}:
            basket_adjustments.append(
                {
                    "type": line_type,
                    "name": name,
                    "amount": round(amount, 2),
                    "currency": currency,
                    "source": "azure_structured",
                }
            )
            continue

        unresolved_adjustments.append(
            {
                "type": "unknown_adjustment",
                "name": name,
                "amount": round(amount, 2),
                "reason": (
                    "Negative/unusual adjustment detected without enough "
                    "evidence to associate it safely."
                ),
                "source": "azure_structured",
            }
        )

    return {
        "items": items,
        "basket_adjustments": basket_adjustments,
        "unresolved_adjustments": unresolved_adjustments,
        "applied_adjustments": applied_adjustments,
    }


def _normalize_match_text(value: str | None) -> str:
    text = normalize_text(value)

    # Remove prices and punctuation that often appear in raw OCR lines.
    text = re.sub(r"[-+]?\d+(?:[.,]\d{1,2})?", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _similarity(left: str, right: str) -> float:
    left_n = _normalize_match_text(left)
    right_n = _normalize_match_text(right)

    if not left_n or not right_n:
        return 0.0

    if left_n in right_n or right_n in left_n:
        return 1.0

    return SequenceMatcher(
        None,
        left_n,
        right_n,
    ).ratio()


def _raw_adjustment_candidates(raw_text: str) -> list[dict]:
    candidates = []

    for index, raw_line in enumerate((raw_text or "").splitlines()):
        line = raw_line.strip()

        if not line:
            continue

        parsed_amount = parse_money_from_text(line)

        if parsed_amount is None:
            continue

        line_type = classify_receipt_line(
            name=line,
            total_price=parsed_amount,
            unit_price=None,
        )

        if line_type == "product":
            continue

        amount = adjustment_amount(
            total_price=parsed_amount,
            unit_price=None,
            adjustment_type=line_type,
        )

        candidates.append(
            {
                "raw_line_index": index,
                "raw_line": line,
                "type": line_type,
                "amount": round(amount, 2),
            }
        )

    return candidates


def _match_products_to_raw_lines(
    raw_text: str,
    items: list[dict],
) -> dict[int, int]:
    """
    Map product indexes to the most likely raw OCR line indexes.
    """
    raw_lines = [
        line.strip()
        for line in (raw_text or "").splitlines()
    ]

    result: dict[int, int] = {}
    used_line_indexes: set[int] = set()

    for item_index, item in enumerate(items):
        best_line_index = None
        best_score = 0.0

        for raw_index, raw_line in enumerate(raw_lines):
            if raw_index in used_line_indexes:
                continue

            score = _similarity(
                item.get("base_name", ""),
                raw_line,
            )

            if score > best_score:
                best_score = score
                best_line_index = raw_index

        # Conservative threshold: only use a mapping when the textual
        # evidence is reasonably strong.
        if best_line_index is not None and best_score >= 0.58:
            result[item_index] = best_line_index
            used_line_indexes.add(best_line_index)

    return result


def _has_matching_item_adjustment(
    item: dict,
    amount: float,
) -> bool:
    target = round(abs(amount), 2)

    for adjustment in item.get("applied_adjustments", []):
        existing = round(
            abs(safe_float(adjustment.get("amount"), 0.0)),
            2,
        )

        if abs(existing - target) <= MONEY_TOLERANCE:
            return True

    return False


def _has_matching_basket_adjustment(
    basket_adjustments: list[dict],
    amount: float,
    adjustment_type: str,
) -> bool:
    target = round(abs(amount), 2)

    for adjustment in basket_adjustments:
        if adjustment.get("type") != adjustment_type:
            continue

        existing = round(
            abs(safe_float(adjustment.get("amount"), 0.0)),
            2,
        )

        if abs(existing - target) <= MONEY_TOLERANCE:
            return True

    return False


def _find_raw_target_item(
    candidate_line: int,
    product_line_map: dict[int, int],
) -> int | None:
    possible_targets = []

    for item_index, product_line in product_line_map.items():
        if product_line >= candidate_line:
            continue

        distance = candidate_line - product_line

        # A line-level discount is normally directly below or close to
        # the product it modifies. Keep this deliberately conservative.
        if distance <= 3:
            possible_targets.append(
                (distance, item_index)
            )

    if not possible_targets:
        return None

    possible_targets.sort()
    return possible_targets[0][1]


def recover_missing_adjustments_from_raw_text(
    raw_text: str,
    structure: dict,
) -> None:
    """
    Recover explicit adjustments visible in raw Azure OCR text but missing
    from Azure's structured Items collection.

    Important:
    - We only recover when the raw text explicitly looks like an adjustment.
    - We do not infer an adjustment merely because totals differ.
    - Line discounts are de-duplicated against the adjustment already
      attached to the *same product*. This matters when two products have
      identical discount amounts.
    - Item-level recovery is attached only when a matching product line
      immediately precedes the discount within a small OCR distance.
    """
    if not raw_text:
        return

    items = structure["items"]
    applied_adjustments = structure["applied_adjustments"]
    basket_adjustments = structure["basket_adjustments"]
    unresolved_adjustments = structure["unresolved_adjustments"]

    candidates = _raw_adjustment_candidates(raw_text)
    product_line_map = _match_products_to_raw_lines(
        raw_text=raw_text,
        items=items,
    )

    for candidate in candidates:
        amount = candidate["amount"]
        candidate_type = candidate["type"]

        if candidate_type == "line_discount":
            target_index = _find_raw_target_item(
                candidate_line=candidate["raw_line_index"],
                product_line_map=product_line_map,
            )

            if target_index is not None:
                target_item = items[target_index]

                # If Azure structured Items already supplied the same
                # discount for this exact product, this raw line is only
                # corroborating evidence, not another discount.
                if _has_matching_item_adjustment(
                    target_item,
                    amount,
                ):
                    continue

                if can_attach_line_adjustment(
                    target_item,
                    amount,
                ):
                    _apply_adjustment_to_item(
                        target_item,
                        amount,
                        source_name=candidate["raw_line"],
                        source="azure_raw_text",
                    )

                    applied_adjustments.append(
                        {
                            "type": "line_discount",
                            "name": candidate["raw_line"],
                            "amount": round(amount, 2),
                            "target_item": target_item["base_name"],
                            "source": "azure_raw_text",
                        }
                    )
                    continue

            unresolved_adjustments.append(
                {
                    "type": "line_discount",
                    "name": candidate["raw_line"],
                    "amount": round(amount, 2),
                    "reason": (
                        "Explicit discount exists in raw OCR text, but no "
                        "safe product association was found."
                    ),
                    "source": "azure_raw_text",
                }
            )
            continue

        if candidate_type in {"basket_discount", "surcharge"}:
            if _has_matching_basket_adjustment(
                basket_adjustments=basket_adjustments,
                amount=amount,
                adjustment_type=candidate_type,
            ):
                continue

            basket_adjustments.append(
                {
                    "type": candidate_type,
                    "name": candidate["raw_line"],
                    "amount": round(amount, 2),
                    "currency": (
                        items[0]["currency"]
                        if items
                        else "RON"
                    ),
                    "source": "azure_raw_text",
                }
            )
            continue

        unresolved_adjustments.append(
            {
                "type": candidate_type,
                "name": candidate["raw_line"],
                "amount": round(amount, 2),
                "reason": (
                    "Adjustment exists in raw OCR text but could not be "
                    "classified or associated safely."
                ),
                "source": "azure_raw_text",
            }
        )

def apply_basket_adjustments_proportionally(
    structure: dict,
) -> None:
    """
    Apply only *explicitly classified* basket-level adjustments across
    products proportionally.

    This is different from using the receipt total difference as a discount:
    no adjustment is invented. It must already be present in structured or
    raw OCR evidence.
    """
    items = structure["items"]
    basket_adjustments = structure["basket_adjustments"]

    if not items or not basket_adjustments:
        return

    total_adjustment = round(
        sum(
            safe_float(adjustment.get("amount"), 0.0)
            for adjustment in basket_adjustments
        ),
        2,
    )

    if abs(total_adjustment) <= MONEY_TOLERANCE:
        return

    base_total = round(
        sum(
            max(safe_float(item.get("total_price"), 0.0), 0.0)
            for item in items
        ),
        2,
    )

    if base_total <= 0:
        structure["unresolved_adjustments"].append(
            {
                "type": "basket_adjustment",
                "name": "Basket adjustments",
                "amount": total_adjustment,
                "reason": "Cannot distribute adjustment across zero-value items.",
                "source": "calculated",
            }
        )
        return

    # Do not apply a discount that would make the whole basket negative.
    if total_adjustment < 0 and abs(total_adjustment) > base_total + MONEY_TOLERANCE:
        structure["unresolved_adjustments"].append(
            {
                "type": "basket_adjustment",
                "name": "Basket adjustments",
                "amount": total_adjustment,
                "reason": "Basket discount exceeds detected product total.",
                "source": "calculated",
            }
        )
        return

    remaining = total_adjustment

    for index, item in enumerate(items):
        if index == len(items) - 1:
            allocated = round(remaining, 2)
        else:
            weight = (
                max(safe_float(item.get("total_price"), 0.0), 0.0)
                / base_total
            )
            allocated = round(total_adjustment * weight, 2)
            remaining = round(remaining - allocated, 2)

        item["basket_adjustment_total"] = round(
            safe_float(item.get("basket_adjustment_total"), 0.0)
            + allocated,
            2,
        )

        item["total_price"] = round(
            safe_float(item.get("total_price"), 0.0)
            + allocated,
            2,
        )

        quantity = safe_float(item.get("quantity"), 1.0)

        if quantity:
            item["unit_price"] = round(
                item["total_price"] / quantity,
                2,
            )

        item.setdefault("applied_adjustments", []).append(
            {
                "type": "basket_allocation",
                "name": "Basket adjustment allocation",
                "amount": allocated,
                "source": "calculated",
            }
        )


def finalize_receipt_items(structure: dict) -> list[dict]:
    finalized = []

    for item in structure["items"]:
        item["name"] = _format_item_name(item)

        finalized.append(
            {
                "name": item["name"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "total_price": item["total_price"],
                "currency": item["currency"],
                "original_total_price": item["original_total_price"],
                "line_adjustment_total": item["line_adjustment_total"],
                "basket_adjustment_total": item["basket_adjustment_total"],
                "applied_adjustments": item["applied_adjustments"],
            }
        )

    return finalized


def _validation_status(
    items_total: float,
    receipt_total: float,
    unresolved_adjustments: list[dict],
) -> str:
    difference = round(items_total - receipt_total, 2)

    if abs(difference) <= MONEY_TOLERANCE:
        if unresolved_adjustments:
            return "valid_with_unresolved_metadata"

        return "valid"

    if difference > 0:
        return "unresolved_discount_or_missing_adjustment"

    return "unresolved_charge_or_missing_item"


def process_document_with_azure_receipt_direct(
    db: Session,
    document_id: int
) -> dict:
    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    if not document:
        raise ValueError("Document not found.")

    if not document.case_id:
        raise ValueError("Document is not linked to a case.")

    provider = AzureReceiptOCRProvider()

    if not provider.is_configured():
        raise ValueError(
            "Azure Receipt OCR provider is not configured. "
            "Check AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
            "AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )

    external_request = ExternalOCRRequest(
        document_id=document.id,
        case_id=document.case_id,
        reason="direct_azure_receipt_ocr",
        provider_status="processing",
        preferred_provider="azure_receipt",
        local_confidence=None,
        local_name_quality=None,
        local_detected_total=None,
        local_receipt_total=None,
        error_message=None,
    )

    db.add(external_request)
    db.commit()
    db.refresh(external_request)

    started_at = datetime.utcnow()

    try:
        result = provider.process_document(
            document=document,
            request=external_request
        )

        result_dict = model_to_dict(result)
        raw_ocr_text = getattr(
            provider,
            "last_raw_content",
            "",
        ) or ""

        existing_item_ids = [
            item_id
            for item_id, in db.query(ReceiptItem.id)
            .filter(ReceiptItem.document_id == document.id)
            .all()
        ]

        if existing_item_ids:
            db.query(SplitBillItemAssignment).filter(
                SplitBillItemAssignment.receipt_item_id.in_(
                    existing_item_ids
                )
            ).delete(synchronize_session=False)

        db.query(ReceiptItem).filter(
            ReceiptItem.document_id == document.id
        ).delete(synchronize_session=False)

        structure = build_receipt_structure(
            raw_items=result.items,
            default_currency=result.currency or "RON",
        )

        # Azure may omit a visible discount/adjustment from structured Items.
        # Recover only adjustments explicitly present in raw OCR text.
        recover_missing_adjustments_from_raw_text(
            raw_text=raw_ocr_text,
            structure=structure,
        )

        # Explicit basket-level adjustments are allocated proportionally so
        # selectable split-bill items still reconcile to the receipt total.
        apply_basket_adjustments_proportionally(
            structure=structure,
        )

        net_items = finalize_receipt_items(
            structure=structure,
        )

        saved_items = []

        for net_item in net_items:
            item = ReceiptItem(
                case_id=document.case_id,
                document_id=document.id,
                name=net_item["name"],
                quantity=net_item["quantity"],
                unit_price=net_item["unit_price"],
                total_price=net_item["total_price"],
                currency=net_item["currency"],
                selected_by_user=False,
            )

            db.add(item)
            saved_items.append(item)

        receipt_total = round(
            float(result.receipt_total or 0),
            2,
        )

        items_total = round(
            sum(
                float(item.total_price or 0)
                for item in saved_items
            ),
            2,
        )

        signed_difference = round(
            items_total - receipt_total,
            2,
        )

        total_difference = round(
            abs(signed_difference),
            2,
        )

        is_valid = total_difference <= MONEY_TOLERANCE

        validation_status = _validation_status(
            items_total=items_total,
            receipt_total=receipt_total,
            unresolved_adjustments=structure["unresolved_adjustments"],
        )

        warnings = []

        if not is_valid:
            warnings.append(
                "Receipt total does not match the sum of resolved items. "
                "Pruvio did not invent a missing discount or charge."
            )

        if structure["unresolved_adjustments"]:
            warnings.append(
                f"{len(structure['unresolved_adjustments'])} adjustment(s) "
                "could not be associated safely."
            )

        document.document_type = "receipt"
        document.ocr_text = "\n".join(
            f"{item.name} {item.total_price:+.2f} {item.currency}"
            for item in saved_items
        )

        audit_payload = {
            "provider_result": result_dict,
            "raw_ocr_text": raw_ocr_text,
            "adjustments": {
                "applied": structure["applied_adjustments"],
                "basket": structure["basket_adjustments"],
                "unresolved": structure["unresolved_adjustments"],
            },
            "validation": {
                "receipt_total": receipt_total,
                "items_total": items_total,
                "signed_difference": signed_difference,
                "status": validation_status,
            },
        }

        external_request.provider_status = "completed"
        external_request.external_result_json = json.dumps(
            audit_payload,
            ensure_ascii=False,
            default=str,
        )
        external_request.error_message = None

        db.commit()

        for item in saved_items:
            db.refresh(item)

        duration_ms = int(
            (datetime.utcnow() - started_at).total_seconds() * 1000
        )

        return {
            "document_id": document.id,
            "case_id": document.case_id,
            "external_ocr_request_id": external_request.id,
            "provider": result.provider,
            "provider_status": external_request.provider_status,
            "duration_ms": duration_ms,
            "merchant_name": result.merchant_name,
            "items_replaced": True,
            "items_count": len(saved_items),
            "receipt_total": receipt_total,
            "items_total": items_total,
            "signed_difference": signed_difference,
            "total_difference": total_difference,
            "is_valid": is_valid,
            "validation_status": validation_status,
            "currency": result.currency or "RON",
            "provider_confidence": result.provider_confidence,
            "warnings": warnings,
            "adjustments": {
                "applied": structure["applied_adjustments"],
                "basket": structure["basket_adjustments"],
                "unresolved": structure["unresolved_adjustments"],
            },
            "items": [
                {
                    "id": item.id,
                    "case_id": item.case_id,
                    "document_id": item.document_id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                    "currency": item.currency,
                    "selected_by_user": item.selected_by_user,
                    "created_at": item.created_at,
                }
                for item in saved_items
            ],
        }

    except Exception as error:
        external_request.provider_status = "failed"
        external_request.error_message = str(error)

        db.commit()

        raise ValueError(f"Azure Receipt OCR failed: {error}")
