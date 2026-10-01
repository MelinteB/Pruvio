import hashlib
import hmac
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.db.database import get_db
from app.services.phone_otp_service import process_whatsapp_status, whatsapp_otp_enabled

router = APIRouter()


@router.get("/whatsapp/otp", response_class=PlainTextResponse, include_in_schema=False)
def verify_webhook(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    expected = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if not whatsapp_otp_enabled() or not expected or mode != "subscribe" or not hmac.compare_digest(token, expected):
        raise HTTPException(403, "Webhook verification failed.")
    return challenge


@router.post("/whatsapp/otp", include_in_schema=False)
async def status_webhook(request: Request, db=Depends(get_db)):
    secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if not whatsapp_otp_enabled() or not secret:
        raise HTTPException(503, "WhatsApp OTP webhook is not configured.")
    raw = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("x-hub-signature-256", "")):
        raise HTTPException(401, "Invalid webhook signature.")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Invalid webhook payload.")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid webhook payload.")
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("metadata", {}).get("phone_number_id") != os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
                continue
            for status in value.get("statuses", []):
                process_whatsapp_status(db, status)
    return {"status": "ok"}

