import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from nicegui import ui

from app.db.database import Base, engine, ensure_compatibility_schema

# Import every model before create_all so new tables are created on fresh installs.
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.message import Message
from app.models.reminder import Reminder
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.receipt_profile import ReceiptProfile
from app.models.receipt_correction import ReceiptCorrection
from app.models.external_ocr_usage import ExternalOCRUsage
from app.models.receipt_item import ReceiptItem
from app.models.verification_code import VerificationCode
from app.models.whatsapp_event import WhatsAppEvent

from app.api.users import router as users_router
from app.api.cases import router as cases_router
from app.api.webhook import router as webhook_router
from app.api.documents import router as documents_router
from app.api.split_bill_sessions import router as split_bill_sessions_router
from app.api.receipt_profiles import router as receipt_profiles_router
from app.api.split_bill import router as split_bill_router
from app.api.external_ocr import router as external_ocr_router
from app.api.onboarding_otp import router as onboarding_otp_router
from app.api.standalone import router as standalone_router

from app.ui.home_ui import setup_home_ui
from app.ui.account_ui import setup_account_ui
from app.ui.register_ui import setup_register_ui
from app.ui.history_ui import setup_history_ui
from app.ui.legal_ui import setup_legal_ui
from app.ui.support_ui import setup_support_ui
from app.ui.upload_ui import setup_upload_ui
from app.ui.receipt_ui import setup_receipt_ui
from app.ui.split_bill_widget_ui import setup_split_bill_widget_ui
from app.ui.split_bill_session_widget_ui import setup_split_bill_session_widget_ui


Base.metadata.create_all(bind=engine)
ensure_compatibility_schema()

app = FastAPI(
    title="Pruvio Core",
    description="""
Pruvio is a standalone mobile-first receipt assistant.

Upload a receipt, extract and validate items with OCR, translate foreign item
names to English, and create a shareable split-bill session. WhatsApp remains an
optional legacy integration and is disabled unless WHATSAPP_ENABLED=true.
""",
    version="3.0.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(onboarding_otp_router, prefix="/onboarding/otp", tags=["Onboarding OTP"])
app.include_router(split_bill_sessions_router, prefix="/split-bill", tags=["Split Bill Sessions"])
app.include_router(cases_router, prefix="/cases", tags=["Cases"])
app.include_router(webhook_router, prefix="/webhook", tags=["Webhook"])
app.include_router(documents_router, prefix="/documents", tags=["Documents"])
app.include_router(split_bill_router, prefix="/split-bill", tags=["Split Bill"])
app.include_router(receipt_profiles_router, prefix="/receipt-profiles", tags=["Receipt Profiles"])
app.include_router(external_ocr_router, prefix="/external-ocr", tags=["External OCR"])
app.include_router(standalone_router, prefix="/app", tags=["Standalone App"])


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


if _enabled("WHATSAPP_ENABLED", "false"):
    from app.api.whatsapp import router as whatsapp_router
    app.include_router(whatsapp_router, prefix="/webhook", tags=["WhatsApp"])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Pruvio Core",
        "mode": "standalone",
        "whatsapp_enabled": _enabled("WHATSAPP_ENABLED", "false"),
        "database": "connected",
    }


@app.get("/debug/database")
def debug_database():
    return {
        "database_url_present": bool(os.getenv("DATABASE_URL")),
        "database_dialect": engine.dialect.name,
        "database_driver": engine.dialect.driver,
    }


@app.get("/s/{token}")
def short_split_bill_link(token: str):
    return RedirectResponse(
        url=f"/split-bill/sessions/{token}/join",
        status_code=302,
    )


setup_home_ui()
setup_register_ui()
setup_account_ui()
setup_history_ui()
setup_legal_ui()
setup_support_ui()
setup_upload_ui()
setup_receipt_ui()
setup_split_bill_widget_ui()  # legacy single-case view kept for compatibility
setup_split_bill_session_widget_ui()

ui.run_with(
    app,
    storage_secret=os.getenv("PRUVIO_STORAGE_SECRET", "pruvio-local-dev-secret-change-me"),
)
