from app.models.document import Document


def classify_document_from_text(text: str) -> dict:
    normalized_text = text.lower()

    restaurant_keywords = [
        "restaurant",
        "bar",
        "cafe",
        "bistro",
        "nota",
        "bon fiscal",
        "total",
        "masa",
        "ospatar",
        "tips",
        "tip",
        "tva",
        "cash",
        "card"
    ]

    invoice_keywords = [
        "invoice",
        "factura",
        "furnizor",
        "client",
        "cui",
        "iban",
        "serie factura",
        "nr factura",
        "total de plata"
    ]

    refund_keywords = [
        "refund",
        "return",
        "retur",
        "reclamatie",
        "complaint",
        "warranty",
        "garantie",
        "money back",
        "nu am primit",
        "produs defect"
    ]

    subscription_keywords = [
        "subscription",
        "abonament",
        "renewal",
        "recurenta",
        "monthly",
        "charged",
        "cancel"
    ]

    qr_payment_keywords = [
        "revolut.me",
        "send me money",
        "payment link",
        "pay",
        "qr"
    ]

    if any(keyword in normalized_text for keyword in restaurant_keywords):
        return {
            "document_type": "receipt",
            "suggested_module": "split_bill",
            "confidence": 0.85,
            "reason": "Document contains restaurant or receipt-related keywords."
        }

    if any(keyword in normalized_text for keyword in refund_keywords):
        return {
            "document_type": "claim_document",
            "suggested_module": "refund_claim",
            "confidence": 0.80,
            "reason": "Document contains refund, return, claim or warranty keywords."
        }

    if any(keyword in normalized_text for keyword in subscription_keywords):
        return {
            "document_type": "subscription_document",
            "suggested_module": "subscription",
            "confidence": 0.75,
            "reason": "Document contains subscription or recurring payment keywords."
        }

    if any(keyword in normalized_text for keyword in invoice_keywords):
        return {
            "document_type": "invoice",
            "suggested_module": "refund_claim",
            "confidence": 0.65,
            "reason": "Document looks like an invoice. It may be useful for a claim or payment case."
        }

    if any(keyword in normalized_text for keyword in qr_payment_keywords):
        return {
            "document_type": "qr_code",
            "suggested_module": "payment_assist",
            "confidence": 0.80,
            "reason": "Document contains payment link or QR-related keywords."
        }

    return {
        "document_type": "unknown",
        "suggested_module": "unknown",
        "confidence": 0.20,
        "reason": "No clear document pattern detected."
    }


def classify_document(document: Document) -> dict:
    text_parts = []

    if document.document_type:
        text_parts.append(document.document_type)

    if document.original_filename:
        text_parts.append(document.original_filename)

    if document.mime_type:
        text_parts.append(document.mime_type)

    if document.ocr_text:
        text_parts.append(document.ocr_text)

    combined_text = " ".join(text_parts)

    result = classify_document_from_text(combined_text)

    if document.document_type and document.document_type != "unknown":
        if document.document_type == "receipt":
            result["document_type"] = "receipt"
            result["suggested_module"] = "split_bill"
            result["confidence"] = max(result["confidence"], 0.90)
            result["reason"] = "Document was uploaded as receipt."

        if document.document_type == "invoice":
            result["document_type"] = "invoice"
            result["suggested_module"] = "refund_claim"
            result["confidence"] = max(result["confidence"], 0.70)
            result["reason"] = "Document was uploaded as invoice."

        if document.document_type == "qr_code":
            result["document_type"] = "qr_code"
            result["suggested_module"] = "payment_assist"
            result["confidence"] = max(result["confidence"], 0.85)
            result["reason"] = "Document was uploaded as QR code."

    return result