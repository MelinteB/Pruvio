import os

from app.models.document import Document
from app.models.external_ocr_request import ExternalOCRRequest
from app.schemas.external_ocr import ExternalOCRMockResult
from app.services.ocr_providers.mock_provider import MockExternalOCRProvider


PROVIDERS = {
    "mock_external_ocr": MockExternalOCRProvider()
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
            f"External OCR provider '{provider_name}' is not configured. "
            f"Available providers: {available}"
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

    for provider_name in PROVIDERS.keys():
        providers.append(
            {
                "provider_name": provider_name,
                "is_default": provider_name == default_provider,
                "status": "configured"
            }
        )

    return providers