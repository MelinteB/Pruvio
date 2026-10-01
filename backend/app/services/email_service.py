import os
import smtplib
import ssl
from html import escape
from urllib.parse import urlparse

import httpx
from email.message import EmailMessage


def verification_email_html(code: str, ttl_minutes: int) -> str:
    """Match the app's Pruvs identity, with readable text if images are blocked."""
    base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlparse(base_url)
    logo = ""
    if parsed.scheme == "https" and parsed.hostname:
        logo_url = escape(base_url + "/static/pruvs-logo.png", quote=True)
        logo = f'<img src="{logo_url}" width="164" alt="Pruvs" style="display:block;border:0;max-width:100%;height:auto;margin:0 0 20px">'
    return f'''<!doctype html>
<html lang="en"><body style="margin:0;padding:24px 12px;background:#f5f8ff;color:#0a1435;font-family:Arial,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="480" cellspacing="0" cellpadding="0" style="width:100%;max-width:480px;background:#ffffff;border:1px solid #e0e8f6;border-top:4px solid #0756df;border-radius:16px">
<tr><td style="padding:32px">{logo}
<h1 style="margin:0 0 12px;font-size:24px;line-height:1.3;color:#0a1435">Your Pruvs verification code</h1>
<p style="margin:0 0 24px;color:#61708b;line-height:1.6">Enter this code in the app to confirm your request.</p>
<p style="margin:0 0 24px;padding:20px 12px;background:#eaf2ff;border-radius:12px;text-align:center;font-size:32px;font-weight:bold;letter-spacing:6px;color:#0756df">{escape(str(code))}</p>
<p style="margin:0;color:#61708b;font-size:14px;line-height:1.6">This code expires in {escape(str(ttl_minutes))} minutes. Do not share it with anyone.</p>
<p style="margin:18px 0 0;color:#61708b;font-size:12px;line-height:1.6">If you did not request this code, you can ignore this email.</p>
</td></tr></table></td></tr></table></body></html>'''


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
                    "from": sender, "to": [email], "subject": "Your Pruvs verification code",
                    "text": f"Your Pruvs verification code is {code}. It expires in {ttl_minutes} minutes. Do not share this code.",
                    "html": verification_email_html(code, ttl_minutes),
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
    message["Subject"] = "Your Pruvs verification code"
    message["From"] = from_email
    message["To"] = email
    message.set_content(
        f"Your Pruvs verification code is {code}.\n\n"
        f"The code expires in {ttl_minutes} minutes. "
        "If you did not request this code, you can ignore this email."
    )
    message.add_alternative(verification_email_html(code, ttl_minutes), subtype="html")

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
