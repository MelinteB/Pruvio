import base64
import logging
import mimetypes
import os
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel

from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.schemas.external_ocr import ExternalOCRMockItem, ExternalOCRMockResult
from app.services.ocr_providers.base import ExternalOCRProvider


logger = logging.getLogger(__name__)


class OpenAIReceiptLine(BaseModel):
    name: str
    quantity: float
    unit_price: float | None = None
    total_price: float
    currency: str


class OpenAIReceiptExtraction(BaseModel):
    merchant_name: str | None = None
    receipt_total: float
    currency: str
    provider_confidence: float
    items: list[OpenAIReceiptLine]


class OpenAIReceiptOCRProvider(ExternalOCRProvider):
    """OpenAI fallback receipt extractor for Pruvs."""

    provider_name = "openai_receipt"

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_RECEIPT_MODEL", "gpt-6-luna")
        self.timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
        self.max_output_tokens = int(
            os.getenv("OPENAI_RECEIPT_MAX_OUTPUT_TOKENS", "5000")
        )
        self.image_detail = os.getenv(
            "OPENAI_RECEIPT_IMAGE_DETAIL", "high"
        ).strip().lower()
        self.pdf_detail = os.getenv(
            "OPENAI_RECEIPT_PDF_DETAIL", "high"
        ).strip().lower()
        self.last_usage: dict = {}

        if self.image_detail not in {"low", "high", "original", "auto"}:
            self.image_detail = "high"
        if self.pdf_detail not in {"low", "high", "auto"}:
            self.pdf_detail = "high"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _client(self) -> OpenAI:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")
        return OpenAI(api_key=self.api_key, timeout=self.timeout_seconds)

    def _file_content_part(self, file_path: Path) -> dict:
        encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")

        if file_path.suffix.lower() == ".pdf":
            return {
                "type": "input_file",
                "filename": file_path.name,
                "file_data": f"data:application/pdf;base64,{encoded}",
                "detail": self.pdf_detail,
            }

        mime_type, _ = mimetypes.guess_type(file_path.name)
        mime_type = mime_type or "image/jpeg"
        if not mime_type.startswith("image/"):
            raise ValueError(
                f"OpenAI fallback does not support '{file_path.suffix}' files."
            )

        return {
            "type": "input_image",
            "image_url": f"data:{mime_type};base64,{encoded}",
            "detail": self.image_detail,
        }

    @staticmethod
    def _prompt() -> str:
        return """Extract this receipt for the Pruvs split-bill application.

Return only data represented by the structured schema.

Rules:
1. Extract merchant name when visible.
2. receipt_total is the final amount actually payable by the customer.
3. Detect the ISO currency code, for example RON, EUR, USD or GBP.
4. Extract every purchased product/service line in printed order.
5. quantity is purchased quantity. Never confuse package size, volume, weight,
   VAT rate, product code or barcode with quantity.
6. unit_price is unit price when visible/determinable. If quantity is 1 and only
   the line amount is printed, the line amount may be used as unit_price.
7. total_price is the amount for that line.
8. Do not create purchased items for subtotal, VAT summaries, payment methods,
   card details, cash, change, loyalty points, fiscal IDs or informational lines.
9. If a discount clearly belongs to one product, prefer the product's net amount
   after that discount. Do not attach a discount to an unrelated item.
10. Never invent text, prices, quantities, totals or currency.
11. provider_confidence must be between 0 and 1 and reflect confidence in the
    complete structured extraction."""

    def process_document(
        self,
        document: Document,
        request: ExternalOCRRequest,
    ) -> ExternalOCRMockResult:
        if not self.is_configured():
            raise ValueError(
                "OpenAI receipt fallback is not configured. "
                "Set OPENAI_API_KEY and OPENAI_RECEIPT_MODEL."
            )

        file_path = Path(document.path)
        if not file_path.exists():
            raise ValueError("Document file does not exist on disk.")

        response = self._client().responses.parse(
            model=self.model,
            reasoning={"effort": "none"},
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise receipt extraction engine. "
                        "Never infer values that are not visible in the document."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        self._file_content_part(file_path),
                        {"type": "input_text", "text": self._prompt()},
                    ],
                },
            ],
            text_format=OpenAIReceiptExtraction,
            max_output_tokens=self.max_output_tokens,
            store=False,
        )

        extraction = response.output_parsed
        if extraction is None:
            raise ValueError("OpenAI returned no structured receipt extraction.")
        if not extraction.items:
            raise ValueError("OpenAI did not detect receipt line items.")

        currency = (extraction.currency or "RON").strip().upper()
        confidence = max(
            0.0, min(1.0, float(extraction.provider_confidence or 0.0))
        )

        items: list[ExternalOCRMockItem] = []
        for raw_item in extraction.items:
            name = (raw_item.name or "").strip()
            if not name:
                continue

            quantity = float(raw_item.quantity or 1.0)
            if quantity <= 0:
                quantity = 1.0

            total_price = float(raw_item.total_price or 0.0)
            unit_price = (
                float(raw_item.unit_price)
                if raw_item.unit_price is not None
                else (total_price / quantity if quantity else total_price)
            )
            item_currency = (raw_item.currency or currency).strip().upper()

            items.append(
                ExternalOCRMockItem(
                    name=name,
                    quantity=round(quantity, 3),
                    unit_price=round(unit_price, 2),
                    total_price=round(total_price, 2),
                    currency=item_currency,
                )
            )

        if not items:
            raise ValueError("OpenAI extraction contained no usable receipt items.")

        usage = getattr(response, "usage", None)
        self.last_usage = {
            "model": self.model,
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        logger.info(
            "OpenAI receipt fallback completed: model=%s input=%s output=%s items=%s",
            self.model,
            self.last_usage.get("input_tokens"),
            self.last_usage.get("output_tokens"),
            len(items),
        )

        return ExternalOCRMockResult(
            provider=self.provider_name,
            merchant_name=extraction.merchant_name,
            receipt_total=round(float(extraction.receipt_total), 2),
            currency=currency,
            provider_confidence=round(confidence, 2),
            pages_processed=1,
            items=items,
        )
