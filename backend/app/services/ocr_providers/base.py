from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.schemas.external_ocr import ExternalOCRMockResult


class ExternalOCRProvider:
    provider_name = "base_provider"

    def is_configured(self) -> bool:
        return True

    def get_status(self) -> str:
        if self.is_configured():
            return "configured"

        return "not_configured"

    def process_document(
        self,
        document: Document,
        request: ExternalOCRRequest
    ) -> ExternalOCRMockResult:
        raise NotImplementedError(
            "External OCR providers must implement process_document()."
        )