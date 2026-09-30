import os

from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.schemas.external_ocr import ExternalOCRMockResult
from app.services.ocr_providers.mock_provider import MockExternalOCRProvider
from app.services.ocr_providers.azure_receipt_provider import AzureReceiptOCRProvider


PROVIDERS = {
    "mock_external_ocr": MockExternalOCRProvider(),
    "azure_receipt": AzureReceiptOCRProvider()
}


def get_default_provider_name() -> str:
    return os.getenv(
        "DEFAULT_EXTERNAL_OCR_PROVIDER",
        "mock_external_ocr"
    )


def get_provider(provider_name: str):
    provider = PROVIDERS.get(provider_name)

    if not provider:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(
            f"External OCR provider '{provider_name}' is not registered. "
            f"Available providers: {available}"
        )

    if not provider.is_configured():
        raise ValueError(
            f"External OCR provider '{provider_name}' is not configured."
        )

    return provider


def choose_provider_name(request: ExternalOCRRequest) -> str:
    if request.preferred_provider:
        return request.preferred_provider

    return get_default_provider_name()


def process_external_ocr_with_provider(
    document: Document,
    request: ExternalOCRRequest
) -> ExternalOCRMockResult:
    provider_name = choose_provider_name(request)
    provider = get_provider(provider_name)

    return provider.process_document(
        document=document,
        request=request
    )


def list_configured_providers() -> list[dict]:
    default_provider = get_default_provider_name()

    providers = []

    for provider_name, provider in PROVIDERS.items():
        providers.append(
            {
                "provider_name": provider_name,
                "is_default": provider_name == default_provider,
                "status": provider.get_status()
            }
        )

    return providers