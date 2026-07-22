from fastapi import FastAPI

from app.db.database import Base, engine
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.message import Message
from app.models.reminder import Reminder

from app.api.users import router as users_router
from app.api.cases import router as cases_router
from app.api.webhook import router as webhook_router
from app.api.documents import router as documents_router
from app.models.receipt_item import ReceiptItem
from app.api.split_bill import router as split_bill_router
from app.models.receipt_profile import ReceiptProfile
from app.models.receipt_correction import ReceiptCorrection
from app.api.receipt_profiles import router as receipt_profiles_router

from app.models.external_ocr_request import ExternalOCRRequest
from app.api.external_ocr import router as external_ocr_router
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Pruvio Core",
    description="""
Pruvio is a WhatsApp-first modular platform.

Users send receipts, invoices, screenshots, QR codes, PDFs and text messages.

Pruvio analyzes the content, identifies the user's intent and activates the appropriate service module.
""",
    version="1.0.0"
)

app.include_router(
    users_router,
    prefix="/users",
    tags=["Users"]
)

app.include_router(
    cases_router,
    prefix="/cases",
    tags=["Cases"]
)

app.include_router(
    webhook_router,
    prefix="/webhook",
    tags=["Webhook"]
)

app.include_router(
    documents_router,
    prefix="/documents",
    tags=["Documents"]
)

app.include_router(
    split_bill_router,
    prefix="/split-bill",
    tags=["Split Bill"]
)

app.include_router(
    receipt_profiles_router,
    prefix="/receipt-profiles",
    tags=["Receipt Profiles"]
)

app.include_router(
    external_ocr_router,
    prefix="/external-ocr",
    tags=["External OCR"]
)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Pruvio Core",
        "database": "connected"
    }