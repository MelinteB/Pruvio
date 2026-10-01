import os
import smtplib
import ssl

import httpx
from email.message import EmailMessage


def is_email_delivery_configured() -> bool:
    if os.getenv("EMAIL_PROVIDER", "smtp").lower() == "resend":
        return bool(os.getenv("RESEND_API_KEY") and os.getenv("EMAIL_FROM"))
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL"))


def send_email_verification_code(email: str, code: str, ttl_minutes: int) -> dict:
    provider = os.getenv("EMAIL_PROVIDER", "smtp").lower()
    if provider == "resend":
        api_key, sender = os.getenv("RESEND_API_KEY"), os.getenv("EMAIL_FROM")
        if not api_key or not sender:
            return {"sent": False, "provider": "resend", "status": "not_configured", "to": email}
        try:
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                response = client.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {api_key}"}, json={
                    "from": sender, "to": [email], "subject": "Your Pruvio verification code",
                    "text": f"Your Pruvio verification code is {code}. It expires in {ttl_minutes} minutes. Do not share this code.",
                })
            data = response.json()
            if response.is_success and data.get("id"):
                return {"sent": True, "provider": "resend", "status": "queued", "to": email, "message_id": data["id"]}
        except (httpx.HTTPError, ValueError):
            pass
        return {"sent": False, "provider": "resend", "status": "failed", "to": email,
                "reason": "Email could not be accepted. Check the email provider settings."}
    if provider != "smtp":
        return {"sent": False, "provider": provider, "status": "not_configured", "to": email}
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
        smtp_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
        smtp_class = smtplib.SMTP_SSL if smtp_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=20) as server:
            if use_tls and not smtp_ssl:
                server.starttls(context=ssl.create_default_context())
            if username:
                server.login(username, password or "")
            server.send_message(message)
    except Exception as error:
        return {
            "sent": False,
            "provider": "smtp",
            "status": "failed",
            "to": email,
            "reason": "SMTP delivery failed. Check the email provider settings.",
        }

    return {"sent": True, "provider": "smtp", "status": "sent", "to": email}
