from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.webhook import IncomingTestMessage
from app.schemas.user import UserCreate
from app.schemas.case import CaseCreate
from app.schemas.message import MessageCreate
from app.services.user_service import (
    get_user_by_phone,
    create_user,
    activate_user,
    block_user
)
from app.services.case_service import (
    get_open_case_for_user,
    create_case,
    update_case_module,
    update_case_status
)
from app.services.message_service import create_message
from app.services.module_router import (
    detect_module_from_text,
    get_module_welcome_message
)

router = APIRouter()


JOIN_MESSAGE = """
Welcome to Pruvio 👋

Pruvio is a WhatsApp-first assistant that helps you process receipts, invoices, screenshots, QR codes, PDFs and claims.

To start using Pruvio, reply:

YES - to join and accept processing of the documents you send
STOP - to cancel
"""


ACTIVE_MESSAGE = """
You are now registered in Pruvio ✅

Send me a receipt, invoice, screenshot, QR code, PDF or text message and I will help you process it.
"""


BLOCKED_MESSAGE = """
No problem. You will not receive messages from Pruvio.

If you want to join later, send START.
"""


@router.post("/test")
def test_incoming_message(
    incoming: IncomingTestMessage,
    db: Session = Depends(get_db)
):
    message = incoming.message.strip().lower()

    user = get_user_by_phone(db, incoming.phone_number)

    if not user:
        user = create_user(
            db,
            UserCreate(
                phone_number=incoming.phone_number,
                name=incoming.name
            )
        )

        return {
            "phone_number": incoming.phone_number,
            "user_status": user.status,
            "allowed_to_continue": False,
            "reply": JOIN_MESSAGE
        }

    if user.status == "pending_join":
        if message in ["yes", "da", "accept", "join", "start"]:
            user = activate_user(db, user)

            return {
                "phone_number": incoming.phone_number,
                "user_status": user.status,
                "allowed_to_continue": True,
                "reply": ACTIVE_MESSAGE
            }

        if message in ["stop", "no", "nu", "cancel"]:
            user = block_user(db, user)

            return {
                "phone_number": incoming.phone_number,
                "user_status": user.status,
                "allowed_to_continue": False,
                "reply": BLOCKED_MESSAGE
            }

        return {
            "phone_number": incoming.phone_number,
            "user_status": user.status,
            "allowed_to_continue": False,
            "reply": JOIN_MESSAGE
        }

    if user.status == "blocked":
        if message in ["start", "join", "yes"]:
            user.status = "pending_join"
            db.commit()
            db.refresh(user)

            return {
                "phone_number": incoming.phone_number,
                "user_status": user.status,
                "allowed_to_continue": False,
                "reply": JOIN_MESSAGE
            }

        return {
            "phone_number": incoming.phone_number,
            "user_status": user.status,
            "allowed_to_continue": False,
            "reply": BLOCKED_MESSAGE
        }

    if user.status == "active":
        detected = detect_module_from_text(incoming.message)

        case = get_open_case_for_user(db, user.id)

        if not case:
            case = create_case(
                db,
                CaseCreate(
                    user_id=user.id,
                    module=detected["module"],
                    status="waiting_for_input"
                )
            )
        else:
            if case.module == "unknown" and detected["module"] != "unknown":
                case = update_case_module(db, case, detected["module"])

            case = update_case_status(db, case, "waiting_for_input")

        saved_message = create_message(
            db,
            MessageCreate(
                case_id=case.id,
                direction="incoming",
                content=incoming.message
            )
        )

        reply = get_module_welcome_message(case.module)

        create_message(
            db,
            MessageCreate(
                case_id=case.id,
                direction="outgoing",
                content=reply
            )
        )

        return {
            "phone_number": incoming.phone_number,
            "user_status": user.status,
            "allowed_to_continue": True,
            "case_id": case.id,
            "incoming_message_id": saved_message.id,
            "suggested_module": case.module,
            "confidence": detected["confidence"],
            "reason": detected["reason"],
            "reply": reply
        }

    return {
        "phone_number": incoming.phone_number,
        "user_status": user.status,
        "allowed_to_continue": False,
        "reply": "Unknown user status"
    }