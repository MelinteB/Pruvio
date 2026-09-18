import hashlib
import hmac
import json
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.models.whatsapp_event import WhatsAppEvent
from app.services.onboarding_otp_service import normalize_phone_number
from app.services.whatsapp_onboarding_service import (
    ensure_pending_whatsapp_user,
    get_pending_user_prompt,
    get_user_by_whatsapp_phone,
    handle_whatsapp_onboarding_text,
)
from app.services.whatsapp_receipt_service import process_whatsapp_receipt
from app.services.whatsapp_service import (
    send_whatsapp_text_message,
    send_whatsapp_typing_indicator,
)


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


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256 when WHATSAPP_APP_SECRET is configured."""
    app_secret = os.getenv("WHATSAPP_APP_SECRET")

    if not app_secret:
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    received_signature = signature_header.split("=", 1)[1]
    expected_signature = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received_signature, expected_signature)


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
                        "media_id": media_object.get("id") if media_object else None,
                        "mime_type": media_object.get("mime_type") if media_object else None,
                        "filename": media_object.get("filename") if media_object else None,
                        "caption": media_object.get("caption") if media_object else None,
                        "raw": message,
                    }
                )

    return messages


def _claim_message(db: Session, message: dict[str, Any]) -> WhatsAppEvent | None:
    message_id = message.get("message_id")

    if not message_id:
        return None

    event = WhatsAppEvent(
        message_id=message_id,
        sender_phone=message.get("from"),
        message_type=message.get("type"),
        status="processing",
    )

    db.add(event)

    try:
        db.commit()
        db.refresh(event)
        return event
    except IntegrityError:
        db.rollback()
        return None


def _complete_event(db: Session, event: WhatsAppEvent | None):
    if not event:
        return

    event.status = "completed"
    event.completed_at = datetime.utcnow()
    event.error_message = None
    db.commit()


def _fail_event(db: Session, event: WhatsAppEvent | None, error: Exception):
    if not event:
        return

    event.status = "failed"
    event.completed_at = datetime.utcnow()
    event.error_message = str(error)[:2000]
    db.commit()


def _send_reply(sender: str, text: str | None):
    if not text:
        return

    try:
        send_whatsapp_text_message(
            to_phone_number=sender,
            message=text,
        )
    except Exception as error:
        print(f"WhatsApp reply failed: {error}")


def _active_user_greeting(user: User) -> str:
    first_name = (user.name or "").strip().split(" ")[0]
    greeting = f"Salut, {first_name} 👋" if first_name else "Salut 👋"

    return (
        f"{greeting}\n\n"
        "Trimite-mi o poza sau un PDF cu bonul. "
        "Dupa procesare deschizi nota in Pruvio, alegi numarul de participanti "
        "si distribui invitatia direct din pagina notei."
    )


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    if not verify_webhook_signature(
        raw_body=raw_body,
        signature_header=request.headers.get("x-hub-signature-256"),
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    payload = json.loads(raw_body or b"{}")
    messages = extract_whatsapp_messages(payload)

    processed_count = 0
    duplicate_count = 0

    for message in messages:
        sender = message.get("from")

        if not sender:
            continue

        event = _claim_message(db=db, message=message)

        if message.get("message_id") and not event:
            duplicate_count += 1
            continue

        try:
            try:
                send_whatsapp_typing_indicator(message.get("message_id"))
            except Exception as typing_error:
                print(f"WhatsApp typing indicator failed: {typing_error}")

            message_type = message.get("type")
            text = (message.get("text") or "").strip()
            contact_name = message.get("contact_name")

            if message_type == "text":
                onboarding = handle_whatsapp_onboarding_text(
                    db=db,
                    sender_phone=sender,
                    contact_name=contact_name,
                    text=text,
                )

                if onboarding["handled"]:
                    _send_reply(sender, onboarding.get("reply"))
                    _complete_event(db, event)
                    processed_count += 1
                    continue

                user = onboarding["user"]
                normalized_text = text.lower()

                if normalized_text in {
                    "start", "hi", "hello", "salut", "buna", "bună",
                    "bon", "split", "nota", "ajutor", "help",
                }:
                    _send_reply(sender, _active_user_greeting(user))
                else:
                    _send_reply(
                        sender,
                        _active_user_greeting(user),
                    )

                _complete_event(db, event)
                processed_count += 1
                continue

            if message_type in {"image", "document"}:
                user = get_user_by_whatsapp_phone(db, sender)

                if not user:
                    user = ensure_pending_whatsapp_user(
                        db=db,
                        phone_number=sender,
                        contact_name=contact_name,
                    )
                    _send_reply(sender, get_pending_user_prompt(user))
                    _complete_event(db, event)
                    processed_count += 1
                    continue

                if user.status != "active":
                    _send_reply(sender, get_pending_user_prompt(user))
                    _complete_event(db, event)
                    processed_count += 1
                    continue

                media_id = message.get("media_id")

                if not media_id:
                    _send_reply(
                        sender,
                        "Am primit fisierul, dar nu il pot identifica. Trimite-l din nou.",
                    )
                    _complete_event(db, event)
                    processed_count += 1
                    continue

                # Important privacy boundary: media is downloaded only after the
                # sender has been confirmed as an active Pruvio user.
                result = process_whatsapp_receipt(
                    db=db,
                    sender_phone=sender,
                    contact_name=contact_name,
                    media_id=media_id,
                    mime_type=message.get("mime_type"),
                    filename=message.get("filename"),
                )

                if result["status"] == "onboarding_required":
                    _send_reply(sender, result["message"])
                    _complete_event(db, event)
                    processed_count += 1
                    continue

                if result["status"] == "needs_confirmation":
                    _send_reply(sender, result["message"])
                    _complete_event(db, event)
                    processed_count += 1
                    continue

                merchant = result.get("merchant_name") or "Bon"
                total = float(result.get("receipt_total") or 0)
                currency = result.get("currency") or "RON"
                items_count = result.get("items_count") or 0
                owner_url = result.get("owner_widget_url")

                reply_parts = [
                    "Bon procesat ✅",
                    "",
                    f"{merchant} · {total:.2f} {currency}",
                    f"{items_count} produse detectate",
                ]

                if owner_url:
                    reply_parts.extend(
                        [
                            "",
                            "Deschide nota pentru verificare, participanti si distribuire:",
                            owner_url,
                        ]
                    )

                _send_reply(sender, "\n".join(reply_parts))
                _complete_event(db, event)
                processed_count += 1
                continue

            _send_reply(
                sender,
                "Momentan pot procesa mesaje text, poze cu bonuri si PDF-uri.",
            )
            _complete_event(db, event)
            processed_count += 1

        except Exception as error:
            print(f"WhatsApp processing failed: {error}")
            _fail_event(db, event, error)
            _send_reply(
                sender,
                "A aparut o problema la procesare. Incearca din nou peste cateva momente.",
            )

    return {
        "status": "received",
        "messages_count": len(messages),
        "processed_count": processed_count,
        "duplicate_count": duplicate_count,
    }
