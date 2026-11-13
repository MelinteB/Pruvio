"""v7.1.53: currency recognition and safe receipt-currency corrections.

All cases are isolated fakes; no customer database or OCR provider is touched.
"""
from types import SimpleNamespace
import pytest

from app.models.case import Case
from app.models.receipt_item import ReceiptItem
from app.models.external_ocr_request import ExternalOCRRequest
from app.models.split_bill_session import SplitBillSession
from app.services.receipt_currency_service import normalize_currency, set_receipt_currency


@pytest.mark.parametrize("input_value, expected", [
    ("RON", "RON"),
    ("ron", "RON"),
    (" LEI ", "RON"),
    ("lei", "RON"),
    ("EUR", "EUR"),
    ("USD", "USD"),
    ("MDL", "MDL"),
    ("", None),
    (None, None),
    ("—", None),
    ("XXX", None),
    ("XYZ", None),
    ("R0N", None),
])
def test_recognizes_known_currencies_and_romanian_leu_alias(input_value, expected):
    assert normalize_currency(input_value) == expected


class FakeQuery:
    def __init__(self, obj, multiple=False):
        self.obj = obj
        self.multiple = multiple

    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.obj

    def all(self):
        return self.obj if self.multiple else []


class FakeDB:
    def __init__(self, raw_currency):
        self.case = SimpleNamespace(id=11, user_id=7)
        self.items = [SimpleNamespace(currency=raw_currency, total_price=49.63, quantity=1)]
        self.commits = 0
        self.has_split = False

    def query(self, model):
        if model is Case:
            return FakeQuery(self.case)
        if model is ReceiptItem:
            return FakeQuery(self.items, multiple=True)
        if model is SplitBillSession:
            return FakeQuery(self.has_split or None)
        if model is ExternalOCRRequest:
            return FakeQuery(None)
        raise AssertionError("Unexpected table")

    def commit(self):
        self.commits += 1


def test_leu_alias_is_written_as_iso_code_without_changing_amount():
    db = FakeDB("LEI")
    assert set_receipt_currency(db, 11, 7, "ron") == "RON"
    assert db.items[0].currency == "RON"
    assert db.items[0].total_price == 49.63
    assert db.commits == 1


def test_existing_exact_currency_is_idempotent():
    db = FakeDB("RON")
    assert set_receipt_currency(db, 11, 7, "LEI") == "RON"
    assert db.commits == 0


def test_unknown_detected_currency_requires_owner_confirmation():
    db = FakeDB("XYZ")
    assert set_receipt_currency(db, 11, 7, "EUR") == "EUR"
    assert db.items[0].currency == "EUR"
    assert db.commits == 1


def test_existing_valid_currency_is_not_overwritten():
    db = FakeDB("EUR")
    with pytest.raises(ValueError, match="already has a currency"):
        set_receipt_currency(db, 11, 7, "RON")
    assert db.items[0].currency == "EUR"
    assert db.commits == 0


def test_split_receipt_cannot_have_currency_rewritten():
    db = FakeDB("LEI")
    db.has_split = True
    with pytest.raises(ValueError, match="after a split"):
        set_receipt_currency(db, 11, 7, "RON")
    assert db.items[0].currency == "LEI"
    assert db.commits == 0
