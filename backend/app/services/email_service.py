import os
import smtplib
from email.message import EmailMessage


def is_email_delivery_configured() -> bool:
    return bool(
        os.getenv("SMTP_HOST")
        and os.getenv("SMTP_FROM_EMAIL")
    )


def send_email_verification_code(
    email: str,
    code: str,
    ttl_minutes: int,
) -> dict:
    """Send a verification code to the email address itself.

    This is intentionally separate from WhatsApp: an email address is only
    verified if the secret is delivered to the email channel.
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM_EMAIL")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not host or not from_email:
        return {
            "sent": False,
            "reason": "Email delivery is not configured.",
        }

    message = EmailMessage()
    message["Subject"] = "Codul tau de verificare Pruvio"
    message["From"] = from_email
    message["To"] = email
    message.set_content(
        "Codul tau de verificare Pruvio este: "
        f"{code}\n\nCodul expira in {ttl_minutes} minute. "
        "Daca nu ai solicitat acest cod, ignora acest mesaj."
    )

    with smtplib.SMTP(host, port, timeout=20) as server:
        if use_tls:
            server.starttls()
        if username:
            server.login(username, password or "")
        server.send_message(message)

    return {
        "sent": True,
        "to": email,
    }
