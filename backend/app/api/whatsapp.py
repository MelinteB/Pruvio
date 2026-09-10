import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.whatsapp_service import send_whatsapp_text_message


router = APIRouter()


@router.get("/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    expected_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="WHATSAPP_VERIFY_TOKEN is not configured."
        )

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        return int(hub_challenge) if str(hub_challenge).isdigit() else hub_challenge

    raise HTTPException(
        status_code=403,
        detail="Webhook verification failed."
    )


def extract_whatsapp_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            contacts = value.get("contacts", [])
            contact_name = None

            if contacts:
                profile = contacts[0].get("profile", {})
                contact_name = profile.get("name")

            for message in value.get("messages", []):
                messages.append(
                    {
                        "from": message.get("from"),
                        "type": message.get("type"),
                        "text": (
                            message.get("text", {}).get("body")
                            if message.get("type") == "text"
                            else None
                        ),
                        "message_id": message.get("id"),
                        "timestamp": message.get("timestamp"),
                        "contact_name": contact_name,
                        "raw": message,
                    }
                )

    return messages


@router.post("/whatsapp")
async def receive_whatsapp_webhook(request: Request):
    payload = await request.json()

    messages = extract_whatsapp_messages(payload)

    for message in messages:
        sender = message.get("from")
        message_type = message.get("type")
        text = message.get("text") or ""

        if not sender:
            continue

        if message_type == "text":
            lower_text = text.strip().lower()

            if lower_text in ["start", "hi", "hello", "salut", "buna", "bună"]:
                reply = (
                    "Salut! Sunt Pruvio ✅\n\n"
                    "Trimite-mi o poza cu bonul, iar eu te ajut sa il procesez "
                    "si sa creez nota de plata partajata."
                )
            elif lower_text in ["split", "nota", "bon"]:
                reply = (
                    "Perfect ✅\n\n"
                    "Trimite-mi poza bonului, iar dupa procesare iti voi genera "
                    "un link Pruvio pentru impartirea notei."
                )
            else:
                reply = (
                    "Am primit mesajul tau ✅\n\n"
                    "Pentru test, trimite: start, bon sau split."
                )

            try:
                send_whatsapp_text_message(
                    to_phone_number=sender,
                    message=reply
                )
            except Exception as error:
                print(f"WhatsApp reply failed: {error}")

        else:
            try:
                send_whatsapp_text_message(
                    to_phone_number=sender,
                    message=(
                        "Am primit fisierul tau ✅\n\n"
                        "In pasul urmator voi procesa automat imaginile/PDF-urile "
                        "prin Azure OCR."
                    )
                )
            except Exception as error:
                print(f"WhatsApp media reply failed: {error}")

    return {
        "status": "received",
        "messages_count": len(messages)
    }