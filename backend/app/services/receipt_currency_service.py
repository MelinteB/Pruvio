"""Persist an owner-confirmed currency without changing any receipt amounts."""
import json
import re
from datetime import datetime

from app.models.case import Case
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession

UNKNOWN_CURRENCY = "—"
# Searchable choices: ISO currency codes, not ambiguous symbols.
CURRENCY_OPTIONS = dict(line.split("|", 1) for line in """RON|RON — Romanian leu
EUR|EUR — Euro
USD|USD — US dollar
GBP|GBP — British pound
CHF|CHF — Swiss franc
PLN|PLN — Polish złoty
CZK|CZK — Czech koruna
HUF|HUF — Hungarian forint
BGN|BGN — Bulgarian lev
MDL|MDL — Moldovan leu
DKK|DKK — Danish krone
SEK|SEK — Swedish krona
NOK|NOK — Norwegian krone
ISK|ISK — Icelandic króna
TRY|TRY — Turkish lira
UAH|UAH — Ukrainian hryvnia
RSD|RSD — Serbian dinar
ALL|ALL — Albanian lek
BAM|BAM — Bosnia and Herzegovina convertible mark
MKD|MKD — Macedonian denar
CAD|CAD — Canadian dollar
AUD|AUD — Australian dollar
NZD|NZD — New Zealand dollar
JPY|JPY — Japanese yen
CNY|CNY — Chinese yuan
HKD|HKD — Hong Kong dollar
SGD|SGD — Singapore dollar
INR|INR — Indian rupee
THB|THB — Thai baht
IDR|IDR — Indonesian rupiah
MYR|MYR — Malaysian ringgit
PHP|PHP — Philippine peso
VND|VND — Vietnamese đồng
KRW|KRW — South Korean won
AED|AED — UAE dirham
SAR|SAR — Saudi riyal
QAR|QAR — Qatari riyal
ILS|ILS — Israeli new shekel
EGP|EGP — Egyptian pound
MAD|MAD — Moroccan dirham
ZAR|ZAR — South African rand
KES|KES — Kenyan shilling
NGN|NGN — Nigerian naira
BRL|BRL — Brazilian real
MXN|MXN — Mexican peso
ARS|ARS — Argentine peso
CLP|CLP — Chilean peso
COP|COP — Colombian peso
PEN|PEN — Peruvian sol""".splitlines())


def normalize_currency(value):
    """Accept detected three-letter codes; placeholders are never currencies."""
    code = str(value or "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code) and code not in {"XXX", "UNK", "NAN"}:
        return code
    return None


def set_receipt_currency(db, case_id: int, user_id: int, currency: str) -> str:
    code = normalize_currency(currency)
    if code not in CURRENCY_OPTIONS:
        raise ValueError("Choose a currency from the dropdown.")
    # Serialize with session creation on databases supporting row locks.
    case = db.query(Case).filter(Case.id == case_id).with_for_update().first()
    if not case or case.user_id != user_id:
        raise ValueError("Receipt not found or you are not its owner.")
    items = db.query(ReceiptItem).filter(ReceiptItem.case_id == case_id).all()
    if not items:
        raise ValueError("This receipt has no scanned items.")
    if db.query(SplitBillSession).filter(SplitBillSession.case_id == case_id).first():
        raise ValueError("Currency cannot be changed after a split has been created.")
    current = {normalize_currency(item.currency) for item in items}
    if current != {None}:
        if current == {code}:
            return code  # A repeated save after reconnect is harmless.
        raise ValueError("This receipt already has a currency. Refresh the page.")
    request = (db.query(ExternalOCRRequest)
               .filter(ExternalOCRRequest.case_id == case_id)
               .order_by(ExternalOCRRequest.created_at.desc(), ExternalOCRRequest.id.desc()).first())
    if request:
        try:
            payload = json.loads(request.external_result_json or "{}")
            if not isinstance(payload, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Receipt metadata could not be read. Currency was not changed.")
        # Retain the original provider response for audit/review.
        payload["currency_override"] = code
        payload["currency_confirmed_by"] = user_id
        payload["currency_confirmed_at"] = datetime.utcnow().isoformat()
        request.external_result_json = json.dumps(payload, ensure_ascii=False)
    for item in items:
        item.currency = code
    db.commit()
    return code
