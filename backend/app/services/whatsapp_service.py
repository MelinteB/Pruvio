import os
from typing import Any

import httpx


def is_whatsapp_enabled() -> bool:
    return os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"


def normalize_whatsapp_recipient(phone_number: str) -> str:
    return phone_number.replace("+", "").replace(" ", "").strip()


def send_whatsapp_text_message(
    to_phone_number: str,
    message: str
) -> dict[str, Any]:
    if not is_whatsapp_enabled():
        return {
            "sent": False,
            "reason": "WhatsApp integration is disabled."
        }

    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    graph_api_version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v23.0")

    if not access_token:
        raise ValueError("WHATSAPP_ACCESS_TOKEN is missing.")

    if not phone_number_id:
        raise ValueError("WHATSAPP_PHONE_NUMBER_ID is missing.")

    recipient = normalize_whatsapp_recipient(to_phone_number)

    url = (
        f"https://graph.facebook.com/"
        f"{graph_api_version}/"
        f"{phone_number_id}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": message
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    with httpx.Client(timeout=20) as client:
        response = client.post(
            url,
            json=payload,
            headers=headers
        )

    try:
        response_data = response.json()
    except Exception:
        response_data = {
            "raw_response": response.text
        }

    if response.status_code >= 400:
        raise ValueError(
            f"WhatsApp send failed: {response.status_code} - {response_data}"
        )

    return {
        "sent": True,
        "status_code": response.status_code,
        "response": response_data
    }