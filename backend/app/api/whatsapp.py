import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.whatsapp_receipt_service import process_whatsapp_receipt
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
            detail="WHATSAPP_VERIFY_TOKEN is not configured.",
        )

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        return int(hub_challenge) if str(hub_challenge).isdigit() else hub_challenge

    raise HTTPException(
        status_code=403,
        detail="Webhook verification failed.",
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
                message_type = message.get("type")
                media_object = None

                if message_type in {"image", "document"}:
                    media_object = message.get(message_type, {}) or {}

                messages.append(
                    {
                        "from": message.get("from"),
                        "type": message_type,
                        "text": (
                            message.get("text", {}).get("body")
                            if message_type == "text"
                            else None
                        ),
                        "message_id": message.get("id"),
                        "timestamp": message.get("timestamp"),
                        "contact_name": contact_name,
                        "media_id": (
                            media_object.get("id")
                            if media_object
                            else None
                        ),
                        "mime_type": (
                            media_object.get("mime_type")
                            if media_object
                            else None
                        ),
                        "filename": (
                            media_object.get("filename")
                            if media_object
                            else None
                        ),
                        "caption": (
                            media_object.get("caption")
                            if media_object
                            else None
                        ),
                        "raw": message,
                    }
                )

    return messages


def _send_reply(sender: str, text: str):
    try:
        send_whatsapp_text_message(
            to_phone_number=sender,
            message=text,
        )
    except Exception as error:
        print(f"WhatsApp reply failed: {error}")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
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
                    "Trimite-mi o poza cu bonul, iar eu il procesez "
                    "si iti creez automat nota de plata partajata."
                )
            elif lower_text in ["split", "nota", "bon"]:
                reply = (
                    "Perfect ✅\n\n"
                    "Trimite-mi poza bonului. Dupa procesare iti voi trimite "
                    "linkul Pruvio pentru impartirea notei."
                )
            else:
                reply = (
                    "Am primit mesajul tau ✅\n\n"
                    "Pentru test, trimite: start, bon sau split."
                )

            _send_reply(sender, reply)
            continue

        if message_type in {"image", "document"}:
            media_id = message.get("media_id")

            if not media_id:
                _send_reply(
                    sender,
                    "Am primit mesajul, dar nu am gasit identificatorul fisierului.",
                )
                continue

            _send_reply(
                sender,
                "Am primit bonul ✅ Il procesez acum prin Azure OCR...",
            )

            try:
                result = process_whatsapp_receipt(
                    db=db,
                    sender_phone=sender,
                    contact_name=message.get("contact_name"),
                    media_id=media_id,
                    mime_type=message.get("mime_type"),
                    filename=message.get("filename"),
                )

                if result["status"] == "onboarding_required":
                    _send_reply(sender, result["message"])
                    continue

                if result["status"] == "needs_confirmation":
                    _send_reply(sender, result["message"])
                    continue

                merchant = result.get("merchant_name") or "Bon"
                total = float(result.get("receipt_total") or 0)
                currency = result.get("currency") or "RON"
                items_count = result.get("items_count") or 0
                participants = result.get("expected_participants_count") or 2
                owner_url = result.get("owner_widget_url")
                share_url = result.get("share_url")

                reply_parts = [
                    "Bon procesat cu succes ✅",
                    "",
                    f"Magazin: {merchant}",
                    f"Total: {total:.2f} {currency}",
                    f"Produse: {items_count}",
                    f"Participanti: {participants}",
                ]

                if owner_url:
                    reply_parts.extend(
                        [
                            "",
                            "Deschide nota ta Pruvio:",
                            owner_url,
                        ]
                    )

                if share_url:
                    reply_parts.extend(
                        [
                            "",
                            "Link pentru ceilalti participanti:",
                            share_url,
                        ]
                    )

                _send_reply(sender, "\n".join(reply_parts))

            except Exception as error:
                print(f"WhatsApp receipt processing failed: {error}")
                _send_reply(
                    sender,
                    "Nu am putut procesa bonul. Incearca din nou cu o poza mai clara sau un PDF.",
                )

            continue

        _send_reply(
            sender,
            "Momentan pot procesa mesaje text, poze cu bonuri si PDF-uri.",
        )

    return {
        "status": "received",
        "messages_count": len(messages),
    }
