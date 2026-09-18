import os
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.user import User
from app.services.azure_receipt_direct_service import (
    process_document_with_azure_receipt_direct,
)
from app.services.document_service import save_document_bytes
from app.services.onboarding_otp_service import normalize_phone_number
from app.services.split_bill_session_service import (
    build_share_url,
    build_widget_url,
    create_split_bill_session,
    get_owner_participant,
)
from app.services.whatsapp_service import download_whatsapp_media



MIME_EXTENSION_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def _build_original_filename(
    media_id: str,
    mime_type: str | None,
    supplied_filename: str | None = None,
) -> str:
    if supplied_filename:
        return supplied_filename

    extension = MIME_EXTENSION_MAP.get((mime_type or "").lower())

    if not extension:
        raise ValueError(
            f"Unsupported WhatsApp media type: {mime_type or 'unknown'}"
        )

    return f"whatsapp_{media_id}{extension}"


def process_whatsapp_receipt(
    db: Session,
    sender_phone: str,
    contact_name: str | None,
    media_id: str,
    mime_type: str | None,
    filename: str | None = None,
) -> dict:
    normalized_phone = normalize_phone_number(sender_phone)

    user = (
        db.query(User)
        .filter(User.phone_number == normalized_phone)
        .first()
    )

    if not user:
        return {
            "status": "onboarding_required",
            "message": (
                "Numarul tau nu este inca inregistrat in Pruvio. "
                "Finalizeaza mai intai onboarding-ul Pruvio."
            ),
        }

    if user.status != "active":
        return {
            "status": "onboarding_required",
            "message": (
                "Contul tau Pruvio nu este inca activ. "
                "Finalizeaza verificarea contului si incearca din nou."
            ),
        }

    if contact_name and not user.name:
        user.name = contact_name

    user.last_seen_at = datetime.utcnow()
    db.commit()

    media = download_whatsapp_media(media_id)

    effective_mime_type = media.get("mime_type") or mime_type
    original_filename = _build_original_filename(
        media_id=media_id,
        mime_type=effective_mime_type,
        supplied_filename=filename,
    )

    case = Case(
        user_id=user.id,
        module="split_bill",
        status="processing",
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    document = save_document_bytes(
        db=db,
        case=case,
        file_bytes=media["bytes"],
        original_filename=original_filename,
        mime_type=effective_mime_type,
        document_type="receipt",
    )

    ocr_result = process_document_with_azure_receipt_direct(
        db=db,
        document_id=document.id,
    )
    print(
    "WHATSAPP OCR RESULT:",
    json.dumps(
        ocr_result,
        ensure_ascii=False,
        default=str
    )
)
    if not ocr_result.get("is_valid"):
        case.status = "needs_confirmation"
        db.commit()

        return {
            "status": "needs_confirmation",
            "case_id": case.id,
            "document_id": document.id,
            "message": (
                        "Am procesat bonul, dar totalul nu se potriveste ⚠️\n\n"
                        f"Total bon: {ocr_result.get('receipt_total', 0):.2f} "
                        f"{ocr_result.get('currency', 'RON')}\n"
                        f"Suma produse: {ocr_result.get('items_total', 0):.2f} "
                        f"{ocr_result.get('currency', 'RON')}\n"
                        f"Diferenta: {ocr_result.get('total_difference', 0):.2f} "
                        f"{ocr_result.get('currency', 'RON')}"
                    ),
            "ocr": ocr_result,
        }

    expected_participants_count = int(
        os.getenv("WHATSAPP_DEFAULT_SPLIT_PARTICIPANTS", "2")
    )

    session = create_split_bill_session(
        db=db,
        case_id=case.id,
        owner_user_id=user.id,
        expected_participants_count=expected_participants_count,
    )

    owner_participant = get_owner_participant(
        db=db,
        session=session,
    )

    owner_widget_url = None
    if owner_participant:
        owner_widget_url = build_widget_url(
            token=session.token,
            participant_id=owner_participant.id,
        )

    case.status = "needs_confirmation"
    db.commit()

    return {
        "status": "processed",
        "case_id": case.id,
        "document_id": document.id,
        "session_id": session.id,
        "session_token": session.token,
        "merchant_name": ocr_result.get("merchant_name"),
        "receipt_total": ocr_result.get("receipt_total"),
        "currency": ocr_result.get("currency") or "RON",
        "items_count": ocr_result.get("items_count", 0),
        "expected_participants_count": expected_participants_count,
        "share_url": build_share_url(session.token),
        "owner_widget_url": owner_widget_url,
        "ocr": ocr_result,
    }
