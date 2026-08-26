import os

from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.schemas.external_ocr import ExternalOCRMockResult
from app.services.ocr_providers.base import ExternalOCRProvider


class AzureReceiptOCRProvider(ExternalOCRProvider):
    provider_name = "azure_receipt"

    def __init__(self):
        self.endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        self.api_key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def process_document(
        self,
        document: Document,
        request: ExternalOCRRequest
    ) -> ExternalOCRMockResult:
        """
        Azure Receipt OCR provider placeholder.

        This provider is intentionally not implemented yet.
        It will be connected after Azure credentials are configured.
        """

        if not self.is_configured():
            raise ValueError(
                "Azure Receipt OCR provider is not configured. "
                "Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
                "AZURE_DOCUMENT_INTELLIGENCE_KEY in .env."
            )

        raise NotImplementedError(
            "Azure Receipt OCR integration is not implemented yet."
        )