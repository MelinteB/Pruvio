import os
from typing import Any

import httpx


def is_whatsapp_enabled() -> bool:
    return os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"


def get_whatsapp_config() -> dict[str, Any]:
    return {
        "enabled": is_whatsapp_enabled(),
        "access_token": os.getenv("WHATSAPP_ACCESS_TOKEN"),
        "phone_number_id": os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        "graph_api_version": os.getenv("WHATSAPP_GRAPH_API_VERSION", "v23.0"),
    }


def _require_whatsapp_config() -> dict[str, Any]:
    config = get_whatsapp_config()

    if not config["enabled"]:
        raise ValueError("WhatsApp integration is disabled.")

    if not config["access_token"]:
        raise ValueError("WHATSAPP_ACCESS_TOKEN is missing.")

    if not config["phone_number_id"]:
        raise ValueError("WHATSAPP_PHONE_NUMBER_ID is missing.")

    return config


def normalize_whatsapp_recipient(phone_number: str) -> str:
    return phone_number.replace("+", "").replace(" ", "").strip()


def _post_whatsapp_message(payload: dict[str, Any]) -> dict[str, Any]:
    config = _require_whatsapp_config()
    url = (
        f"https://graph.facebook.com/"
        f"{config['graph_api_version']}/"
        f"{config['phone_number_id']}/messages"
    )

    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        response = client.post(url, json=payload, headers=headers)

    try:
        response_data = response.json()
    except Exception:
        response_data = {"raw_response": response.text}

    if response.status_code >= 400:
        raise ValueError(
            f"WhatsApp request failed: {response.status_code} - {response_data}"
        )

    return {
        "sent": True,
        "status_code": response.status_code,
        "response": response_data,
    }


def send_whatsapp_text_message(
    to_phone_number: str,
    message: str,
) -> dict[str, Any]:
    recipient = normalize_whatsapp_recipient(to_phone_number)

    return _post_whatsapp_message(
        {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": message,
            },
        }
    )


def send_whatsapp_otp_message(
    to_phone_number: str,
    code: str,
    ttl_minutes: int = 10,
) -> dict[str, Any]:
    """Send onboarding OTP.

    WHATSAPP_OTP_MODE=text is convenient for the Meta test environment.
    In production use template mode with an approved AUTHENTICATION template.
    """
    mode = os.getenv("WHATSAPP_OTP_MODE", "text").strip().lower()

    if mode != "template":
        return send_whatsapp_text_message(
            to_phone_number=to_phone_number,
            message=(
                f"Codul tau Pruvio este {code}. "
                f"Expira in {ttl_minutes} minute. "
                "Nu comunica acest cod altor persoane."
            ),
        )

    recipient = normalize_whatsapp_recipient(to_phone_number)
    template_name = os.getenv(
        "WHATSAPP_OTP_TEMPLATE_NAME",
        "pruvio_authentication_code",
    )
    language = os.getenv("WHATSAPP_OTP_TEMPLATE_LANGUAGE", "ro")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": code},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [
                        {"type": "text", "text": code},
                    ],
                },
            ],
        },
    }

    return _post_whatsapp_message(payload)


def send_whatsapp_typing_indicator(message_id: str | None) -> dict[str, Any] | None:
    if not message_id:
        return None

    return _post_whatsapp_message(
        {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {
                "type": "text",
            },
        }
    )


def retrieve_whatsapp_media_info(media_id: str) -> dict[str, Any]:
    if not media_id:
        raise ValueError("WhatsApp media ID is missing.")

    config = _require_whatsapp_config()

    url = (
        f"https://graph.facebook.com/"
        f"{config['graph_api_version']}/{media_id}"
    )

    headers = {
        "Authorization": f"Bearer {config['access_token']}",
    }

    params = {
        "phone_number_id": config["phone_number_id"],
    }

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        response = client.get(url, params=params, headers=headers)

    try:
        response_data = response.json()
    except Exception:
        response_data = {"raw_response": response.text}

    if response.status_code >= 400:
        raise ValueError(
            f"WhatsApp media lookup failed: "
            f"{response.status_code} - {response_data}"
        )

    media_url = response_data.get("url")

    if not media_url:
        raise ValueError("WhatsApp did not return a media download URL.")

    return response_data


def download_whatsapp_media(media_id: str) -> dict[str, Any]:
    config = _require_whatsapp_config()
    media_info = retrieve_whatsapp_media_info(media_id)

    headers = {
        "Authorization": f"Bearer {config['access_token']}",
    }

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(media_info["url"], headers=headers)

    if response.status_code >= 400:
        raise ValueError(
            f"WhatsApp media download failed: "
            f"{response.status_code} - {response.text[:500]}"
        )

    return {
        "bytes": response.content,
        "mime_type": (
            media_info.get("mime_type")
            or response.headers.get("content-type")
        ),
        "sha256": media_info.get("sha256"),
        "file_size": media_info.get("file_size") or len(response.content),
        "media_id": media_id,
    }
