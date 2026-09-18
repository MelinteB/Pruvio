import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.email_service import send_email_verification_code
from app.services.onboarding_otp_service import (
    activate_user_if_ready,
    create_or_update_pending_user,
    create_verification_code,
    get_otp_ttl_minutes,
    normalize_email,
    normalize_phone_number,
    should_return_debug_code,
    verify_email_otp,
    verify_phone_otp,
)
from app.services.whatsapp_service import send_whatsapp_otp_message


ACCEPT_WORDS = {
    "accept",
    "accepta",
    "acceptă",
    "de acord",
    "agree",
}

RESEND_WORDS = {
    "retrimite",
    "resend",
    "retrimite cod",
}

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
OTP_PATTERN = re.compile(r"^\d{6}$")


def get_user_by_whatsapp_phone(
    db: Session,
    phone_number: str,
) -> User | None:
    normalized_phone = normalize_phone_number(phone_number)
    return (
        db.query(User)
        .filter(User.phone_number == normalized_phone)
        .first()
    )


def ensure_pending_whatsapp_user(
    db: Session,
    phone_number: str,
    contact_name: str | None,
) -> User:
    user = get_user_by_whatsapp_phone(db, phone_number)

    if user:
        if contact_name and not user.name:
            user.name = contact_name
        user.last_seen_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user

    return create_or_update_pending_user(
        db=db,
        phone_number=phone_number,
        display_name=contact_name,
        email=None,
        accepted_terms=False,
    )


def _registration_intro() -> str:
    return (
        "Salut! Sunt Pruvio 👋\n\n"
        "Nu gasesc inca un cont asociat acestui numar. "
        "Pentru inregistrare vom verifica numarul de WhatsApp si adresa de email.\n\n"
        "Raspunde cu ACCEPT pentru a continua."
    )


def _send_phone_code(
    db: Session,
    user: User,
) -> dict:
    _, code = create_verification_code(
        db=db,
        user=user,
        destination_type="phone",
        destination=user.phone_number,
        purpose="onboarding",
    )

    return send_whatsapp_otp_message(
        to_phone_number=user.phone_number,
        code=code,
        ttl_minutes=get_otp_ttl_minutes(),
    )


def _send_email_code(
    db: Session,
    user: User,
) -> tuple[dict, str]:
    if not user.email:
        raise ValueError("Email address is missing.")

    _, code = create_verification_code(
        db=db,
        user=user,
        destination_type="email",
        destination=user.email,
        purpose="onboarding",
    )

    delivery = send_email_verification_code(
        email=user.email,
        code=code,
        ttl_minutes=get_otp_ttl_minutes(),
    )

    return delivery, code


def get_pending_user_prompt(user: User) -> str:
    if not user.accepted_terms:
        return _registration_intro()

    if not user.is_phone_verified:
        return (
            "Finalizeaza verificarea numarului de WhatsApp. "
            "Introdu codul de 6 cifre primit aici sau scrie RETRIMITE."
        )

    if not user.email:
        return (
            "Numarul tau este verificat ✅\n"
            "Scrie adresa de email pe care vrei sa o asociezi contului Pruvio."
        )

    if not user.is_email_verified:
        return (
            f"Mai trebuie sa verificam {user.email}. "
            "Introdu aici codul de 6 cifre primit pe email sau scrie RETRIMITE."
        )

    return "Contul tau Pruvio este aproape gata. Incearca din nou."


def handle_whatsapp_onboarding_text(
    db: Session,
    sender_phone: str,
    contact_name: str | None,
    text: str,
) -> dict:
    """Handle onboarding entirely from the WhatsApp conversation.

    Returns handled=False only when the user is already active and the normal
    assistant flow should continue.
    """
    user = ensure_pending_whatsapp_user(
        db=db,
        phone_number=sender_phone,
        contact_name=contact_name,
    )

    if user.status == "active":
        return {
            "handled": False,
            "user": user,
            "reply": None,
        }

    normalized_text = (text or "").strip()
    normalized_lower = normalized_text.lower()

    if not user.accepted_terms:
        if normalized_lower not in ACCEPT_WORDS:
            return {
                "handled": True,
                "user": user,
                "reply": _registration_intro(),
            }

        user.accepted_terms = True
        user.accepted_terms_at = datetime.utcnow()
        user.last_seen_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        _send_phone_code(db=db, user=user)

        return {
            "handled": True,
            "user": user,
            "reply": None,
        }

    if not user.is_phone_verified:
        if normalized_lower in RESEND_WORDS:
            _send_phone_code(db=db, user=user)
            return {
                "handled": True,
                "user": user,
                "reply": None,
            }

        if not OTP_PATTERN.fullmatch(normalized_text):
            return {
                "handled": True,
                "user": user,
                "reply": get_pending_user_prompt(user),
            }

        try:
            verify_phone_otp(
                db=db,
                phone_number=user.phone_number,
                code=normalized_text,
            )
        except ValueError as error:
            return {
                "handled": True,
                "user": user,
                "reply": f"Codul nu a putut fi verificat: {error}",
            }

        user = get_user_by_whatsapp_phone(db, sender_phone)

        return {
            "handled": True,
            "user": user,
            "reply": (
                "Numarul tau a fost verificat ✅\n"
                "Acum scrie adresa ta de email."
            ),
        }

    if not user.email:
        email = normalize_email(normalized_text)

        if not email or not EMAIL_PATTERN.fullmatch(email):
            return {
                "handled": True,
                "user": user,
                "reply": "Scrie o adresa de email valida, de exemplu nume@example.com.",
            }

        existing_email_user = (
            db.query(User)
            .filter(User.email == email, User.id != user.id)
            .first()
        )
        if existing_email_user:
            return {
                "handled": True,
                "user": user,
                "reply": "Aceasta adresa de email este deja asociata altui cont Pruvio.",
            }

        user.email = email
        user.is_email_verified = False
        db.commit()
        db.refresh(user)

        delivery, debug_code = _send_email_code(db=db, user=user)

        if delivery.get("sent"):
            return {
                "handled": True,
                "user": user,
                "reply": (
                    f"Ti-am trimis un cod la {email}. "
                    "Scrie aici codul de 6 cifre pentru a finaliza inregistrarea."
                ),
            }

        if should_return_debug_code():
            return {
                "handled": True,
                "user": user,
                "reply": (
                    "Email delivery nu este configurat in mediul de test.\n"
                    f"DEV ONLY - cod email: {debug_code}"
                ),
            }

        return {
            "handled": True,
            "user": user,
            "reply": (
                "Nu pot trimite momentan codul pe email. "
                "Configurarea serviciului de email este necesara inainte de activare."
            ),
        }

    if not user.is_email_verified:
        if normalized_lower in RESEND_WORDS:
            delivery, debug_code = _send_email_code(db=db, user=user)

            if delivery.get("sent"):
                return {
                    "handled": True,
                    "user": user,
                    "reply": f"Am retrimis codul la {user.email}.",
                }

            if should_return_debug_code():
                return {
                    "handled": True,
                    "user": user,
                    "reply": f"DEV ONLY - cod email: {debug_code}",
                }

            return {
                "handled": True,
                "user": user,
                "reply": "Nu pot retrimite codul pe email momentan.",
            }

        if not OTP_PATTERN.fullmatch(normalized_text):
            return {
                "handled": True,
                "user": user,
                "reply": get_pending_user_prompt(user),
            }

        try:
            result = verify_email_otp(
                db=db,
                email=user.email,
                code=normalized_text,
            )
        except ValueError as error:
            return {
                "handled": True,
                "user": user,
                "reply": f"Codul nu a putut fi verificat: {error}",
            }

        user = get_user_by_whatsapp_phone(db, sender_phone)
        activate_user_if_ready(db=db, user=user)

        if user.status == "active":
            first_name = (user.name or "").strip().split(" ")[0] or ""
            hello_name = f", {first_name}" if first_name else ""
            return {
                "handled": True,
                "user": user,
                "reply": (
                    f"Cont verificat cu succes ✅\n\nSalut{hello_name}! "
                    "Poti trimite acum un bon sau un PDF pentru a incepe."
                ),
            }

        return {
            "handled": True,
            "user": user,
            "reply": "Verificarea a fost salvata, dar contul nu este inca activ.",
        }

    return {
        "handled": True,
        "user": user,
        "reply": get_pending_user_prompt(user),
    }
