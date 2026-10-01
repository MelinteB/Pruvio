"""Email delivery helpers and inert compatibility hooks for removed phone OTP."""
from datetime import datetime
from app.services.sms_service import send_sms_verification_code  # Legacy import compatibility only.


def whatsapp_otp_enabled() -> bool:
    return False


def send_whatsapp_otp(destination: str, code: str) -> dict:
    raise ValueError("Phone OTP is disabled. Use email verification.")


def send_phone_otp(destination: str, code: str, ttl: int) -> dict:
    raise ValueError("Phone OTP is disabled. Use email verification.")


def process_whatsapp_status(db, status: dict) -> None:
    # Historical callbacks must never trigger SMS delivery after the email-only migration.
    return


def record_delivery(db, row, result: dict) -> None:
    row.delivery_channel = result.get("provider")
    row.delivery_status = result.get("status")
    row.provider_message_id = result.get("message_id")
    if result.get("fallback_from"):
        row.fallback_at = datetime.utcnow()
    db.commit()


def delivery_message(result: dict, destination: str, lang: str = "en") -> str:
    channel = {"whatsapp": "WhatsApp", "twilio": "SMS", "mock": "SMS", "smtp": "email", "resend": "email"}.get(
        result.get("provider"), "OTP")
    if result.get("sent"):
        return (f"Cod acceptat pentru trimitere prin {channel} la {destination}." if lang == "ro"
                else f"Code accepted for delivery by {channel} to {destination}.")
    return (f"Codul nu a fost trimis prin {channel}. Încearcă din nou sau contactează suportul." if lang == "ro"
            else f"Code was not sent by {channel}. Try again or contact support.")

