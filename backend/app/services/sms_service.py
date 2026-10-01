import base64
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_sms_provider() -> str:
    return os.getenv("SMS_PROVIDER", "mock").strip().lower()


def send_sms_verification_code(phone_number: str, code: str, ttl_minutes: int) -> dict:
    provider = get_sms_provider()
    message = f"Your Pruvs verification code is {code}. It expires in {ttl_minutes} minutes."

    if provider == "mock":
        return {
            "sent": False,
            "provider": "mock",
            "status": "debug_only",
            "to": phone_number,
            "reason": "SMS_PROVIDER=mock",
        }

    if provider != "twilio":
        return {
            "sent": False,
            "provider": provider,
            "status": "not_configured",
            "to": phone_number,
            "reason": f"Unsupported SMS provider: {provider}",
        }

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")

    if not account_sid or not auth_token or not from_number:
        return {
            "sent": False,
            "provider": "twilio",
            "status": "not_configured",
            "to": phone_number,
            "reason": "Twilio credentials are incomplete.",
        }

    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = urlencode({"To": phone_number, "From": from_number, "Body": message}).encode("utf-8")
    token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    request = Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
            return {
                "sent": 200 <= response.status < 300,
                "provider": "twilio",
                "status": "queued" if 200 <= response.status < 300 else "failed",
                "message_id": data.get("sid"),
                "to": phone_number,
            }
    except Exception as error:
        return {
            "sent": False,
            "provider": "twilio",
            "status": "failed",
            "to": phone_number,
            "reason": "SMS delivery failed. Check the SMS provider settings.",
        }
