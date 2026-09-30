from datetime import datetime

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.external_ocr_usage import ExternalOCRUsage
from app.models.message import Message
from app.models.passkey_credential import PasskeyCredential
from app.models.receipt_correction import ReceiptCorrection
from app.models.receipt_item import ReceiptItem
from app.models.reminder import Reminder
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_session import SplitBillSession
from app.models.user import User
from app.models.verification_code import VerificationCode
from app.services.onboarding_otp_service import (
    create_verification_code,
    normalize_email,
    normalize_phone_number,
    verify_code,
    _deliver,
    _debug_code,
)
from app.services.password_service import hash_password, verify_password


def update_profile_name(db: Session, user: User, name: str) -> User:
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Name is required.")
    user.name = clean
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def update_preferences(
    db: Session,
    user: User,
    *,
    preferred_language: str,
    notifications_opt_in: bool,
    marketing_opt_in: bool,
) -> User:
    language = (preferred_language or "en").lower()
    if language not in {"en", "ro"}:
        raise ValueError("Unsupported language.")
    user.preferred_language = language
    user.notifications_opt_in = bool(notifications_opt_in)
    user.marketing_opt_in = bool(marketing_opt_in)
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def request_contact_change(db: Session, user: User, channel: str, value: str) -> dict:
    if channel == "email":
        destination = normalize_email(value)
        if not destination:
            raise ValueError("Email is required.")
        existing = db.query(User).filter(User.email == destination, User.id != user.id).first()
        if existing:
            raise ValueError("This email is already used by another account.")
        purpose = "change_email"
    elif channel == "phone":
        destination = normalize_phone_number(value)
        existing = db.query(User).filter(User.phone_number == destination, User.id != user.id).first()
        if existing:
            raise ValueError("This phone number is already used by another account.")
        purpose = "change_phone"
    else:
        raise ValueError("Unsupported verification channel.")

    _, code = create_verification_code(db, user, channel, destination, purpose)
    delivery = _deliver(channel, destination, code)
    return {
        "destination_type": channel,
        "destination": destination,
        "delivery": delivery,
        "debug_otp": _debug_code(code),
    }


def confirm_contact_change(db: Session, user: User, channel: str, value: str, code: str) -> User:
    destination = normalize_email(value) if channel == "email" else normalize_phone_number(value)
    purpose = "change_email" if channel == "email" else "change_phone"
    verified_user = verify_code(
        db,
        destination_type=channel,
        destination=destination,
        code=code,
        purpose=purpose,
    )
    if verified_user.id != user.id:
        raise ValueError("Verification code does not belong to this account.")
    if channel == "email":
        existing = db.query(User).filter(User.email == destination, User.id != user.id).first()
        if existing:
            raise ValueError("This email is already used by another account.")
        user.email = destination
        user.is_email_verified = True
    else:
        existing = db.query(User).filter(User.phone_number == destination, User.id != user.id).first()
        if existing:
            raise ValueError("This phone number is already used by another account.")
        user.phone_number = destination
        user.is_phone_verified = True
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: User, new_password: str, current_password: str | None = None) -> User:
    if user.password_hash and not verify_password(current_password or "", user.password_hash):
        raise ValueError("Current password is incorrect.")
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def request_password_reset(db: Session, email: str) -> dict:
    destination = normalize_email(email)
    if not destination:
        raise ValueError("Enter a valid email address.")
    user = db.query(User).filter(User.email == destination).first()
    if not user or user.status != "active" or not user.is_email_verified:
        raise ValueError("No active verified Pruvio account was found for this email.")
    _, code = create_verification_code(db, user, "email", destination, "password_reset")
    delivery = _deliver("email", destination, code)
    return {
        "destination": destination,
        "delivery": delivery,
        "debug_otp": _debug_code(code),
    }


def confirm_password_reset(db: Session, email: str, code: str, new_password: str) -> User:
    destination = normalize_email(email)
    if not destination:
        raise ValueError("Enter a valid email address.")
    user = verify_code(
        db,
        destination_type="email",
        destination=destination,
        code=code,
        purpose="password_reset",
    )
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def request_account_deletion_otp(db: Session, user: User, channel: str) -> dict:
    if channel == "email":
        if not user.email or not user.is_email_verified:
            raise ValueError("A verified email is required for this channel.")
        destination = user.email
    elif channel == "phone":
        if not user.phone_number or not user.is_phone_verified:
            raise ValueError("A verified phone number is required for this channel.")
        destination = user.phone_number
    else:
        raise ValueError("Channel must be email or phone.")
    _, code = create_verification_code(db, user, channel, destination, "account_delete")
    delivery = _deliver(channel, destination, code)
    return {
        "destination_type": channel,
        "destination": destination,
        "delivery": delivery,
        "debug_otp": _debug_code(code),
    }


def _delete_session(db: Session, session_id: int) -> None:
    db.query(SplitBillItemAssignment).filter(SplitBillItemAssignment.session_id == session_id).delete(synchronize_session=False)
    db.query(SplitBillParticipant).filter(SplitBillParticipant.session_id == session_id).delete(synchronize_session=False)
    db.query(SplitBillSession).filter(SplitBillSession.id == session_id).delete(synchronize_session=False)


def delete_user_completely(db: Session, user: User) -> None:
    user_id = user.id

    # Remove participation from sessions owned by somebody else.
    participant_ids = [row.id for row in db.query(SplitBillParticipant).filter(SplitBillParticipant.user_id == user_id).all()]
    if participant_ids:
        db.query(SplitBillItemAssignment).filter(SplitBillItemAssignment.participant_id.in_(participant_ids)).delete(synchronize_session=False)
        db.query(SplitBillParticipant).filter(SplitBillParticipant.id.in_(participant_ids)).delete(synchronize_session=False)

    # Remove sessions owned by the user.
    owned_session_ids = [row.id for row in db.query(SplitBillSession).filter(SplitBillSession.owner_user_id == user_id).all()]
    for session_id in owned_session_ids:
        _delete_session(db, session_id)

    # Remove all case-scoped data owned by the user.
    case_ids = [row.id for row in db.query(Case).filter(Case.user_id == user_id).all()]
    for case_id in case_ids:
        case_session_ids = [row.id for row in db.query(SplitBillSession).filter(SplitBillSession.case_id == case_id).all()]
        for session_id in case_session_ids:
            _delete_session(db, session_id)

        document_ids = [row.id for row in db.query(Document).filter(Document.case_id == case_id).all()]
        request_ids = [row.id for row in db.query(ExternalOCRRequest).filter(ExternalOCRRequest.case_id == case_id).all()]
        if request_ids:
            db.query(ExternalOCRUsage).filter(ExternalOCRUsage.external_ocr_request_id.in_(request_ids)).delete(synchronize_session=False)
        db.query(ExternalOCRUsage).filter(ExternalOCRUsage.case_id == case_id).delete(synchronize_session=False)
        db.query(ExternalOCRRequest).filter(ExternalOCRRequest.case_id == case_id).delete(synchronize_session=False)
        db.query(ReceiptCorrection).filter(ReceiptCorrection.case_id == case_id).delete(synchronize_session=False)
        db.query(SplitBillItemAssignment).filter(
            SplitBillItemAssignment.receipt_item_id.in_(
                db.query(ReceiptItem.id).filter(ReceiptItem.case_id == case_id)
            )
        ).delete(synchronize_session=False)
        db.query(ReceiptItem).filter(ReceiptItem.case_id == case_id).delete(synchronize_session=False)
        db.query(Message).filter(Message.case_id == case_id).delete(synchronize_session=False)
        db.query(Reminder).filter(Reminder.case_id == case_id).delete(synchronize_session=False)
        if document_ids:
            db.query(Document).filter(Document.id.in_(document_ids)).delete(synchronize_session=False)
        db.query(Case).filter(Case.id == case_id).delete(synchronize_session=False)

    db.query(VerificationCode).filter(VerificationCode.user_id == user_id).delete(synchronize_session=False)
    db.query(PasskeyCredential).filter(PasskeyCredential.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()


def confirm_and_delete_account(db: Session, user: User, channel: str, code: str) -> None:
    if channel == "email":
        destination = user.email
    elif channel == "phone":
        destination = user.phone_number
    else:
        raise ValueError("Channel must be email or phone.")
    if not destination:
        raise ValueError("Verification destination is unavailable.")
    verified_user = verify_code(
        db,
        destination_type=channel,
        destination=destination,
        code=code,
        purpose="account_delete",
    )
    if verified_user.id != user.id:
        raise ValueError("Verification code does not belong to this account.")
    delete_user_completely(db, user)


def _normalize_iban(value: str | None) -> str | None:
    iban = "".join((value or "").upper().split())
    if not iban:
        return None
    if not iban.isalnum() or not 15 <= len(iban) <= 34:
        raise ValueError("Enter a valid IBAN (15 to 34 letters/numbers).")
    return iban


def _normalize_bic(value: str | None) -> str | None:
    bic = "".join((value or "").upper().split())
    if not bic:
        return None
    if not bic.isalnum() or len(bic) not in {8, 11}:
        raise ValueError("BIC/SWIFT must contain 8 or 11 letters/numbers.")
    return bic


def update_payment_details(
    db: Session,
    user: User,
    *,
    recipient_name: str | None,
    iban: str | None,
    bank_name: str | None,
    bic: str | None,
    revolut_link: str | None,
    payment_note: str | None,
) -> User:
    recipient = (recipient_name or "").strip() or None
    bank = (bank_name or "").strip() or None
    note = (payment_note or "").strip() or None
    link = (revolut_link or "").strip()
    if link and not (link.startswith("https://revolut.me/") or link.startswith("https://www.revolut.me/")):
        raise ValueError("Use your Revolut.me payment link, for example https://revolut.me/yourname")

    normalized_iban = _normalize_iban(iban)
    normalized_bic = _normalize_bic(bic)
    has_bank_details = bool(recipient or normalized_iban or bank or normalized_bic)
    if has_bank_details and not normalized_iban:
        raise ValueError("IBAN is required when bank transfer details are saved.")
    if has_bank_details and not recipient:
        raise ValueError("Recipient name is required when bank transfer details are saved.")

    user.payment_recipient_name = recipient
    user.payment_iban = normalized_iban
    user.payment_bank_name = bank
    user.payment_bic = normalized_bic
    user.revolut_payment_link = link or None
    user.payment_note = note
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def update_revolut_payment_link(db: Session, user: User, value: str | None) -> User:
    """Backward-compatible wrapper used by older callers."""
    return update_payment_details(
        db,
        user,
        recipient_name=user.payment_recipient_name,
        iban=user.payment_iban,
        bank_name=user.payment_bank_name,
        bic=user.payment_bic,
        revolut_link=value,
        payment_note=user.payment_note,
    )
