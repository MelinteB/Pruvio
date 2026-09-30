from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.schemas.external_ocr import (
    ExternalOCRMockResult,
    ExternalOCRMockItem
)

from app.services.ocr_providers.base import ExternalOCRProvider

class MockExternalOCRProvider(ExternalOCRProvider):
    provider_name = "mock_provider"

    def process_document(
        self,
        document: Document,
        request: ExternalOCRRequest
    ) -> ExternalOCRMockResult:
        """
        Mock provider used for testing the complete provider-router flow.
        It does not call a real OCR provider.
        It creates a clean external result using the receipt total detected locally.
        Later this will be replaced by Azure / Mindee / AWS providers.
        """
        receipt_total = request.local_receipt_total

        if receipt_total is None:
            receipt_total = request.local_detected_total

        if receipt_total is None:
            receipt_total = 0.0

        receipt_total = round(receipt_total, 2)

        return ExternalOCRMockResult(
            provider=self.provider_name,
            merchant_name="Mock External OCR Merchant",
            receipt_total=receipt_total,
            currency="RON",
            provider_confidence=0.95,
            items=[
                ExternalOCRMockItem(
                    name="Mock External OCR Item",
                    quantity=1.0,
                    unit_price=receipt_total,
                    total_price=receipt_total,
                    currency="RON"
                )
            ]
        )