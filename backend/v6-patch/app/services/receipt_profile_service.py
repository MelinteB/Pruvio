import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.receipt_profile import ReceiptProfile
from app.models.receipt_correction import ReceiptCorrection
from app.models.document import Document
from app.schemas.receipt_profile import (
    ReceiptProfileCreate,
    ReceiptCorrectionCreate
)
from app.services.receipt_format_detector import (
    build_receipt_signature,
    build_receipt_signature_json
)
from app.schemas.receipt_profile import ReceiptProfileUpdate

def update_receipt_profile(
    db: Session,
    profile: ReceiptProfile,
    profile_data: ReceiptProfileUpdate
):
    update_data = profile_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)

    return profile

def get_receipt_profiles(db: Session):
    return (
        db.query(ReceiptProfile)
        .order_by(ReceiptProfile.created_at.desc())
        .all()
    )


def get_receipt_profile_by_id(db: Session, profile_id: int):
    return (
        db.query(ReceiptProfile)
        .filter(ReceiptProfile.id == profile_id)
        .first()
    )


def create_receipt_profile(
    db: Session,
    profile_data: ReceiptProfileCreate
):
    profile = ReceiptProfile(
        merchant_name=profile_data.merchant_name,
        merchant_tax_id=profile_data.merchant_tax_id,
        country=profile_data.country,
        profile_name=profile_data.profile_name,
        profile_signature=profile_data.profile_signature,
        parser_strategy=profile_data.parser_strategy,
        rules_json=profile_data.rules_json,
        status=profile_data.status,
        confidence_score=profile_data.confidence_score,
        updated_at=datetime.utcnow()
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile


def activate_profile(db: Session, profile: ReceiptProfile):
    profile.status = "active"
    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)

    return profile


def find_matching_active_profile(
    db: Session,
    ocr_text: str
) -> ReceiptProfile | None:
    signature = build_receipt_signature(ocr_text)

    merchant_tax_id = signature.get("merchant_tax_id")
    merchant_name = signature.get("merchant_name")

    if merchant_tax_id:
        profile = (
            db.query(ReceiptProfile)
            .filter(
                ReceiptProfile.merchant_tax_id == merchant_tax_id,
                ReceiptProfile.status == "active"
            )
            .order_by(ReceiptProfile.confidence_score.desc())
            .first()
        )

        if profile:
            return profile

    if merchant_name:
        profile = (
            db.query(ReceiptProfile)
            .filter(
                ReceiptProfile.merchant_name == merchant_name,
                ReceiptProfile.status == "active"
            )
            .order_by(ReceiptProfile.confidence_score.desc())
            .first()
        )

        if profile:
            return profile

    generic_profile = (
        db.query(ReceiptProfile)
        .filter(
            ReceiptProfile.profile_name == "Generic Romanian Supermarket Profile",
            ReceiptProfile.status == "active"
        )
        .order_by(ReceiptProfile.confidence_score.desc())
        .first()
    )

    if generic_profile:
        return generic_profile
    
    return None


def create_draft_profile_from_document(
    db: Session,
    document: Document,
    parser_strategy: str = "generic_low_confidence",
    confidence_score: float = 0.0
):
    if not document.ocr_text:
        raise ValueError("Document has no OCR text")

    signature = build_receipt_signature(document.ocr_text)

    merchant_name = signature.get("merchant_name")
    merchant_tax_id = signature.get("merchant_tax_id")

    existing_draft = None

    if merchant_tax_id:
        existing_draft = (
            db.query(ReceiptProfile)
            .filter(
                ReceiptProfile.merchant_tax_id == merchant_tax_id,
                ReceiptProfile.status == "draft"
            )
            .first()
        )

    if existing_draft:
        return existing_draft, False

    rules = {
            "preprocess": {
                "normalize_measurements": True,
                "ignore_keywords": [
                    "tva",
                    "vat",
                    "card",
                    "cash",
                    "numerar",
                    "rest",
                    "bon fiscal",
                    "operator",
                    "casier",
                    "cui",
                    "cod identificare",
                    "ecotaxa"
                ],
                "ignore_line_patterns": [
                    r"^\s*\d{1,6}(?:[.,]\d{1,3})?\s+\w+\s*(?:x|×)\s*\d{1,6}(?:[.,]\d{2})\s*$"
                ],
                "replace_patterns": []
            },
            "item_cleanup": {
                "normalize_measurements": True,
                "ignore_item_names": [
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
                ],
                "remove_name_prefix_patterns": [
                    r"^(lei|lel|lcl|ron)\s+"
                ],
                "remove_name_suffix_patterns": [
                    r"\s+[a-zA-Z]$"
                ],
                "replace_patterns": []
            },
            "requires_review": True
        }

    profile_data = ReceiptProfileCreate(
        merchant_name=merchant_name,
        merchant_tax_id=merchant_tax_id,
        country="RO",
        profile_name=f"Draft profile - {merchant_name or 'Unknown merchant'}",
        profile_signature=build_receipt_signature_json(document.ocr_text),
        parser_strategy=parser_strategy,
        rules_json=json.dumps(rules, ensure_ascii=False),
        status="draft",
        confidence_score=confidence_score
    )

    profile = create_receipt_profile(db, profile_data)

    return profile, True


def save_receipt_correction(
    db: Session,
    document: Document,
    correction_data: ReceiptCorrectionCreate
):
    correction = ReceiptCorrection(
        case_id=correction_data.case_id,
        document_id=correction_data.document_id,
        correction_type="manual",
        original_ocr_text=document.ocr_text,
        wrong_extraction_json=correction_data.wrong_extraction_json,
        corrected_items_json=correction_data.corrected_items_json,
        notes=correction_data.notes
    )

    db.add(correction)
    db.commit()
    db.refresh(correction)

    return correction


def update_profile_success(
    db: Session,
    profile: ReceiptProfile
):
    profile.success_count += 1
    profile.confidence_score = min(profile.confidence_score + 0.05, 1.0)
    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)

    return profile


def update_profile_failure(
    db: Session,
    profile: ReceiptProfile
):
    profile.failure_count += 1
    profile.confidence_score = max(profile.confidence_score - 0.10, 0.0)
    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)

    return profile