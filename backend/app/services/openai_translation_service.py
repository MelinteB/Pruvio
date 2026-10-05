import logging
import os
from dataclasses import dataclass, field

from openai import OpenAI
from pydantic import BaseModel


logger = logging.getLogger(__name__)


@dataclass
class OpenAITranslationOutcome:
    source_language: str | None = None
    translated_names: dict[str, str] = field(default_factory=dict)
    skipped: bool = False
    error: str | None = None
    usage: dict = field(default_factory=dict)


class TranslationExtraction(BaseModel):
    source_language: str
    translations: list[str]


def translate_receipt_item_names_with_openai(
    item_names: list[str],
) -> OpenAITranslationOutcome:
    clean_names = [name.strip() for name in item_names if name and name.strip()]
    if not clean_names:
        return OpenAITranslationOutcome(skipped=True)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    model = os.getenv(
        "OPENAI_TRANSLATION_MODEL",
        os.getenv("OPENAI_RECEIPT_MODEL", "gpt-6-luna"),
    )
    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
    client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    numbered_names = "\n".join(
        f"{index + 1}. {name}" for index, name in enumerate(clean_names)
    )

    response = client.responses.parse(
        model=model,
        reasoning={"effort": "none"},
        input=[
            {
                "role": "system",
                "content": (
                    "You detect receipt language and translate product names. "
                    "Keep brands, model names, sizes, quantities and product codes "
                    "unchanged unless they are ordinary translatable words."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Determine the dominant language of these receipt item names "
                    "using a two-letter ISO language code. If it is Romanian (ro) "
                    "or English (en), return every original name unchanged. "
                    "Otherwise translate every name to English. Return exactly one "
                    "translation per input in the same order.\n\n"
                    f"{numbered_names}"
                ),
            },
        ],
        text_format=TranslationExtraction,
        max_output_tokens=2500,
        store=False,
    )

    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("OpenAI returned no structured translation result.")

    source_language = (parsed.source_language or "").strip().lower()
    usage_obj = getattr(response, "usage", None)
    usage = {
        "model": model,
        "input_tokens": getattr(usage_obj, "input_tokens", None),
        "output_tokens": getattr(usage_obj, "output_tokens", None),
        "total_tokens": getattr(usage_obj, "total_tokens", None),
    }

    if source_language in {"ro", "en"}:
        return OpenAITranslationOutcome(
            source_language=source_language,
            skipped=True,
            usage=usage,
        )

    if len(parsed.translations) != len(clean_names):
        raise ValueError(
            "OpenAI translation result count does not match item count."
        )

    translated_names: dict[str, str] = {}
    for original, translated in zip(clean_names, parsed.translations):
        translated = (translated or "").strip()
        if translated and translated.casefold() != original.casefold():
            translated_names[original] = translated

    logger.info(
        "OpenAI translation fallback completed: model=%s language=%s items=%s",
        model,
        source_language,
        len(clean_names),
    )

    return OpenAITranslationOutcome(
        source_language=source_language or None,
        translated_names=translated_names,
        skipped=False,
        usage=usage,
    )
