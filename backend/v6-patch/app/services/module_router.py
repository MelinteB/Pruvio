def detect_module_from_text(message: str) -> dict:
    text = message.lower()

    split_bill_keywords = [
        "split",
        "bill",
        "restaurant",
        "receipt",
        "nota",
        "bon",
        "masa",
        "tips",
        "tip",
        "revolut"
    ]

    refund_claim_keywords = [
        "refund",
        "claim",
        "return",
        "complaint",
        "reclamatie",
        "retur",
        "garantie",
        "money back",
        "did not receive",
        "nu am primit"
    ]

    subscription_keywords = [
        "subscription",
        "cancel",
        "abonament",
        "charged",
        "plata recurenta",
        "renewal"
    ]

    if any(keyword in text for keyword in split_bill_keywords):
        return {
            "module": "split_bill",
            "confidence": 0.85,
            "reason": "Message contains restaurant/bill/payment keywords."
        }

    if any(keyword in text for keyword in refund_claim_keywords):
        return {
            "module": "refund_claim",
            "confidence": 0.85,
            "reason": "Message contains refund/claim/complaint keywords."
        }

    if any(keyword in text for keyword in subscription_keywords):
        return {
            "module": "subscription",
            "confidence": 0.75,
            "reason": "Message contains subscription/cancellation keywords."
        }

    return {
        "module": "unknown",
        "confidence": 0.20,
        "reason": "No clear module detected."
    }


def get_module_welcome_message(module: str) -> str:
    if module == "split_bill":
        return (
            "I detected a possible restaurant bill split. "
            "Please send a photo of the receipt or the list of items."
        )

    if module == "refund_claim":
        return (
            "I detected a possible refund or claim case. "
            "Please send the invoice, order confirmation and screenshots with the seller."
        )

    if module == "subscription":
        return (
            "I detected a possible subscription issue. "
            "Please send a screenshot of the charge or subscription details."
        )

    return (
        "I received your message. Please send a receipt, invoice, screenshot, QR code or PDF "
        "and I will detect what service module should be used."
    )