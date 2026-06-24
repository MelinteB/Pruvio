from fastapi import FastAPI
app = FastAPI(title="Pruvio Core", description="""Pruvio is a WhatsApp-first modular assistant.
                                                Users send receipts, invoices, screenshots, QR codes, PDFs or text through WhatsApp.
                                                Pruvio detects the intent and activates the right service module.""", 
                                                version="1.0.0")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "Pruvio Core"
    }