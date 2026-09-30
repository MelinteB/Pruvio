import os
from dataclasses import dataclass, field

import requests


SKIP_TRANSLATION_LANGUAGES = {"ro", "en"}


@dataclass
class ReceiptTranslationResult:
    source_language: str | None = None
    translated_names: dict[str, str] = field(default_factory=dict)
    skipped: bool = False
    error: str | None = None


def _translator_headers() -> dict[str, str]:
    key = os.getenv("AZURE_TRANSLATOR_KEY")
    region = os.getenv("AZURE_TRANSLATOR_REGION")

    if not key:
        raise ValueError("AZURE_TRANSLATOR_KEY is not configured.")

    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/json",
    }

    # Required for regional or multi-service resources; optional for global.
    if region:
        headers["Ocp-Apim-Subscription-Region"] = region

    return headers


def _translator_endpoint() -> str:
    return os.getenv(
        "AZURE_TRANSLATOR_ENDPOINT",
        "https://api.cognitive.microsofttranslator.com"
    ).rstrip("/")


def _translation_enabled() -> bool:
    return os.getenv("ENABLE_RECEIPT_TRANSLATION", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def detect_receipt_language(item_names: list[str]) -> str | None:
    clean_names = [name.strip() for name in item_names if name and name.strip()]

    if not clean_names:
        return None

    # Detect once at receipt level. This is more stable than detecting each
    # short product name independently (brands can otherwise look English).
    receipt_text = " | ".join(clean_names)

    response = requests.post(
        f"{_translator_endpoint()}/detect",
        params={"api-version": "3.0"},
        headers=_translator_headers(),
        json=[{"Text": receipt_text}],
        timeout=10,
    )
    response.raise_for_status()

    payload = response.json()
    if not payload:
        return None

    language = payload[0].get("language")
    return language.lower() if language else None


def translate_names_to_english(
    item_names: list[str],
    source_language: str,
) -> dict[str, str]:
    clean_names = [name.strip() for name in item_names if name and name.strip()]

    if not clean_names:
        return {}

    response = requests.post(
        f"{_translator_endpoint()}/translate",
        params={
            "api-version": "3.0",
            "from": source_language,
            "to": "en",
        },
        headers=_translator_headers(),
        json=[{"Text": name} for name in clean_names],
        timeout=15,
    )
    response.raise_for_status()

    payload = response.json()
    translated: dict[str, str] = {}

    for original, result in zip(clean_names, payload):
        translations = result.get("translations") or []
        if not translations:
            continue

        english_name = (translations[0].get("text") or "").strip()
        if english_name and english_name.casefold() != original.casefold():
            translated[original] = english_name

    return translated


def translate_receipt_item_names(item_names: list[str]) -> ReceiptTranslationResult:
    """
    Translation policy for Pruvio:
      * Romanian receipt (ro) -> keep original only.
      * English receipt (en) -> keep original only.
      * Any other detected language -> translate item names to English.

    Translation is non-critical. If Azure Translator is unavailable or not
    configured, OCR processing continues with original item names only.
    """
    if not _translation_enabled():
        return ReceiptTranslationResult(skipped=True)

    if not os.getenv("AZURE_TRANSLATOR_KEY"):
        return ReceiptTranslationResult(
            skipped=True,
            error="Azure Translator is not configured."
        )

    try:
        source_language = detect_receipt_language(item_names)

        if not source_language:
            return ReceiptTranslationResult(
                skipped=True,
                error="Receipt language could not be detected."
            )

        if source_language in SKIP_TRANSLATION_LANGUAGES:
            return ReceiptTranslationResult(
                source_language=source_language,
                skipped=True,
            )

        translated_names = translate_names_to_english(
            item_names=item_names,
            source_language=source_language,
        )

        return ReceiptTranslationResult(
            source_language=source_language,
            translated_names=translated_names,
            skipped=False,
        )

    except Exception as error:
        # Translation must never make receipt OCR fail.
        return ReceiptTranslationResult(
            skipped=True,
            error=str(error),
        )
