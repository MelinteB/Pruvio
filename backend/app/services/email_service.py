import os
import smtplib
from email.message import EmailMessage


def is_email_delivery_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"))


def send_email_verification_code(email: str, code: str, ttl_minutes: int) -> dict:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM_EMAIL")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not host or not from_email:
        return {
            "sent": False,
            "provider": "smtp",
            "status": "not_configured",
            "to": email,
            "reason": "SMTP delivery is not configured.",
        }

    message = EmailMessage()
    message["Subject"] = "Your Pruvio verification code"
    message["From"] = from_email
    message["To"] = email
    message.set_content(
        f"Your Pruvio verification code is {code}.\n\n"
        f"The code expires in {ttl_minutes} minutes. "
        "If you did not request this code, you can ignore this email."
    )

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_tls:
                server.starttls()
            if username:
                server.login(username, password or "")
            server.send_message(message)
    except Exception as error:
        return {
            "sent": False,
            "provider": "smtp",
            "status": "failed",
            "to": email,
            "reason": str(error),
        }

    return {"sent": True, "provider": "smtp", "status": "sent", "to": email}
