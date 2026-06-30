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

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Pruvio Core",
        "database": "connected"
    }