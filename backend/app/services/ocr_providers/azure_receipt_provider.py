import os
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.schemas.external_ocr import (
    ExternalOCRMockResult,
    ExternalOCRMockItem
)
from app.services.ocr_providers.base import ExternalOCRProvider


class AzureReceiptOCRProvider(ExternalOCRProvider):
    provider_name = "azure_receipt"

    def __init__(self):
        self.endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        self.api_key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        self.locale = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_LOCALE", "ro-RO")

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def process_document(
        self,
        document: Document,
        request: ExternalOCRRequest
    ) -> ExternalOCRMockResult:
        if not self.is_configured():
            raise ValueError(
                "Azure Receipt OCR provider is not configured. "
                "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
                "AZURE_DOCUMENT_INTELLIGENCE_KEY in .env."
            )

        file_path = Path(document.path)

        if not file_path.exists():
            raise ValueError("Document file does not exist on disk.")

        client = DocumentIntelligenceClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.api_key)
        )

        with open(file_path, "rb") as receipt_file:
            poller = client.begin_analyze_document(
                "prebuilt-receipt",
                body=receipt_file,
                locale=self.locale
            )

        result = poller.result()

        return self._normalize_azure_result(result)

    def _normalize_azure_result(self, result) -> ExternalOCRMockResult:
        if not getattr(result, "documents", None):
            raise ValueError("Azure returned no receipt documents.")

        receipt = result.documents[0]
        fields = getattr(receipt, "fields", {}) or {}

        merchant_name = self._get_text_field(fields.get("MerchantName"))

        receipt_total = self._get_money_or_number_field(fields.get("Total"))

        if receipt_total is None:
            receipt_total = self._get_money_or_number_field(
                fields.get("TransactionTotal")
            )

        if receipt_total is None:
            raise ValueError("Azure did not detect receipt total.")

        currency = self._get_currency(fields.get("Total")) or "RON"

        items = self._extract_items(fields.get("Items"), currency)

        if not items:
            raise ValueError("Azure did not detect receipt line items.")

        provider_confidence = self._estimate_provider_confidence(
            receipt=receipt,
            items=items
        )

        return ExternalOCRMockResult(
            provider=self.provider_name,
            merchant_name=merchant_name,
            receipt_total=round(receipt_total, 2),
            currency=currency,
            provider_confidence=provider_confidence,
            items=items
        )

    def _extract_items(
        self,
        items_field,
        currency: str
    ) -> list[ExternalOCRMockItem]:
        extracted_items = []

        item_array = self._get_array(items_field)

        for item_field in item_array:
            item_object = self._get_object(item_field)

            name = (
                self._get_text_field(item_object.get("Description"))
                or self._get_text_field(item_object.get("Name"))
                or self._get_text_field(item_object.get("ProductCode"))
            )

            quantity = (
                self._get_number_field(item_object.get("Quantity"))
                or 1.0
            )

            unit_price = (
                self._get_money_or_number_field(item_object.get("Price"))
                or self._get_money_or_number_field(item_object.get("UnitPrice"))
            )

            total_price = (
                self._get_money_or_number_field(item_object.get("TotalPrice"))
                or self._get_money_or_number_field(item_object.get("Amount"))
            )

            if total_price is None and unit_price is not None:
                total_price = unit_price * quantity

            if not name or total_price is None:
                continue

            if unit_price is None:
                unit_price = total_price / quantity if quantity else total_price

            extracted_items.append(
                ExternalOCRMockItem(
                    name=name.strip(),
                    quantity=float(quantity),
                    unit_price=round(float(unit_price), 2),
                    total_price=round(float(total_price), 2),
                    currency=currency
                )
            )

        return extracted_items

    def _get_text_field(self, field) -> str | None:
        if field is None:
            return None

        value = getattr(field, "value", None)

        if value is not None:
            return str(value)

        content = getattr(field, "content", None)

        if content:
            return str(content)

        return None

    def _get_number_field(self, field) -> float | None:
        if field is None:
            return None

        value = getattr(field, "value", None)

        if isinstance(value, (int, float)):
            return float(value)

        content = getattr(field, "content", None)

        if content:
            return self._parse_number(content)

        return None

    def _get_money_or_number_field(self, field) -> float | None:
        if field is None:
            return None

        value = getattr(field, "value", None)

        amount = getattr(value, "amount", None)

        if amount is not None:
            return float(amount)

        if isinstance(value, (int, float)):
            return float(value)

        content = getattr(field, "content", None)

        if content:
            return self._parse_number(content)

        return None

    def _get_currency(self, field) -> str | None:
        if field is None:
            return None

        value = getattr(field, "value", None)

        currency_code = getattr(value, "currency_code", None)

        if currency_code:
            return currency_code

        return None

    def _get_array(self, field) -> list:
        if field is None:
            return []

        value_array = getattr(field, "value_array", None)

        if value_array is not None:
            return value_array

        value = getattr(field, "value", None)

        if isinstance(value, list):
            return value

        return []

    def _get_object(self, field) -> dict:
        if field is None:
            return {}

        value_object = getattr(field, "value_object", None)

        if isinstance(value_object, dict):
            return value_object

        value = getattr(field, "value", None)

        if isinstance(value, dict):
            return value

        return {}

    def _parse_number(self, text: str) -> float | None:
        cleaned = (
            text.replace("RON", "")
            .replace("Lei", "")
            .replace("lei", "")
            .replace(",", ".")
            .strip()
        )

        number_parts = []

        for character in cleaned:
            if character.isdigit() or character == ".":
                number_parts.append(character)

        number_text = "".join(number_parts)

        if not number_text:
            return None

        try:
            return float(number_text)
        except ValueError:
            return None

    def _estimate_provider_confidence(
        self,
        receipt,
        items: list[ExternalOCRMockItem]
    ) -> float:
        receipt_confidence = getattr(receipt, "confidence", None)

        if receipt_confidence is not None:
            return round(float(receipt_confidence), 2)

        if items:
            return 0.85

        return 0.50