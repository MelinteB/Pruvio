import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from nicegui import ui

from app.db.database import Base, engine, ensure_compatibility_schema

# Import every model before create_all so new tables are created on fresh installs.
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.user import User
from app.models.passkey_credential import PasskeyCredential
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
from app.models.trusted_device import TrustedDevice

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
from app.api.account import router as account_router
from app.api.trusted_device import router as device_router

from app.ui.home_ui import setup_home_ui
from app.ui.account_ui import setup_account_ui
from app.ui.register_ui import setup_register_ui
from app.ui.password_reset_ui import setup_password_reset_ui
from app.ui.history_ui import setup_history_ui
from app.ui.legal_ui import setup_legal_ui
from app.ui.support_ui import setup_support_ui
from app.ui.upload_ui import setup_upload_ui
from app.ui.receipt_ui import setup_receipt_ui
from app.ui.split_bill_widget_ui import setup_split_bill_widget_ui
from app.ui.split_bill_session_widget_ui import setup_split_bill_session_widget_ui
from app.services.passkey_service import passkeys_enabled
from app.services.totp_debug_service import totp_debug_enabled
from app.web_domain import canonical_browser_redirect


Base.metadata.create_all(bind=engine)
ensure_compatibility_schema()

app = FastAPI(
    title="Pruvs Core",
    description="""
Pruvs is a standalone mobile-first receipt assistant.

Upload a receipt, extract and validate items with OCR, translate foreign item
names to English, and create a shareable split-bill session. The standalone application supports email-only authentication OTP and does not mount the legacy WhatsApp receipt interface. Pruvs v6.6 adds live auto-saved split selections, participant quantity labels for every assignment, fully-claimed item styling, one-active-account-per-browser protection for split sessions, and serialized live assignment updates. It retains the v6.5 quantity-aware allocations, per-person percentage tips, split history/reopening, derived usernames, branding, email authentication, passkeys, OCR and payment flows.
""",
    version="6.6.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def canonical_domain(request: Request, call_next):
    redirect = canonical_browser_redirect(request)
    if redirect is not None:
        return redirect
    return await call_next(request)

# Public/current API surface shown in /docs.
app.include_router(account_router, prefix="/auth", tags=["Authentication"])
app.include_router(device_router, prefix="/auth")
app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(onboarding_otp_router, prefix="/onboarding/otp", tags=["Registration OTP"])
app.include_router(split_bill_sessions_router, prefix="/split-bill", tags=["Split Bill Sessions"])
app.include_router(standalone_router, prefix="/app", tags=["Receipts"])

# Legacy/internal endpoints remain available for compatibility but are hidden from OpenAPI docs.
app.include_router(cases_router, prefix="/cases", tags=["Cases"], include_in_schema=False)
app.include_router(webhook_router, prefix="/webhook", tags=["Webhook"], include_in_schema=False)
app.include_router(documents_router, prefix="/documents", tags=["Documents"], include_in_schema=False)
app.include_router(split_bill_router, prefix="/split-bill", tags=["Legacy Split Bill"], include_in_schema=False)
app.include_router(receipt_profiles_router, prefix="/receipt-profiles", tags=["Receipt Profiles"], include_in_schema=False)
app.include_router(external_ocr_router, prefix="/external-ocr", tags=["External OCR"], include_in_schema=False)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# WhatsApp is intentionally not mounted in the standalone application.
# Legacy WhatsApp modules remain in the repository for reference only.


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Pruvs Core",
        "mode": "standalone",
        "whatsapp_enabled": False,
        "whatsapp_otp_enabled": False,
        "otp_channels": ["email"],
        "database": "connected",
        "version": "6.6.0",
        "passkeys_enabled": passkeys_enabled(),
        "developer_totp_enabled": totp_debug_enabled(),
    }


@app.get("/debug/database", include_in_schema=False)
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
setup_password_reset_ui()
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
    reconnect_timeout=60.0,
    storage_secret=os.getenv("PRUVIO_STORAGE_SECRET", "pruvio-local-dev-secret-change-me"),
)
