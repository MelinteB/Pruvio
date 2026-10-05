from __future__ import annotations

import re
import shutil
from pathlib import Path


BACKUP_SUFFIX = ".bak_v6_7_openai"


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def patch_requirements(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    backup(path)
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?mi)^\s*openai(?:[<>=!~].*)?$", text):
        print(f"[OK] {path}: OpenAI SDK already present.")
        return
    if text and not text.endswith("\n"):
        text += "\n"
    text += "openai>=2.0.0,<3.0.0\n"
    path.write_text(text, encoding="utf-8")
    print(f"[PATCHED] {path}: added OpenAI SDK.")


def patch_azure_direct(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    backup(path)
    text = path.read_text(encoding="utf-8")

    if "import logging\n" not in text:
        text = text.replace("import json\n", "import json\nimport logging\n", 1)
    if "import os\n" not in text:
        text = text.replace("import logging\n", "import logging\nimport os\n", 1)

    if "def _openai_receipt_fallback_enabled" not in text:
        marker = "\ndef model_to_dict"
        if marker not in text:
            raise RuntimeError(f"Could not find model_to_dict() anchor in {path}.")
        helper = '''

logger = logging.getLogger(__name__)


def _openai_receipt_fallback_enabled() -> bool:
    return os.getenv(
        "OPENAI_RECEIPT_FALLBACK_ENABLED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}


def _run_openai_receipt_fallback(
    db: Session,
    document_id: int,
    azure_error: Exception | str,
) -> dict:
    logger.warning(
        "Azure receipt OCR failed for document_id=%s; trying OpenAI fallback. "
        "Azure error: %s",
        document_id,
        azure_error,
    )

    try:
        # Lazy import avoids a circular import: the OpenAI direct service
        # deliberately reuses this module's existing normalization helpers.
        from app.services.openai_receipt_direct_service import (
            process_document_with_openai_receipt_direct,
        )

        result = process_document_with_openai_receipt_direct(
            db=db,
            document_id=document_id,
            reason="azure_receipt_ocr_fallback",
        )
        result["primary_provider"] = "azure_receipt"
        result["fallback_used"] = True
        return result

    except Exception as openai_error:
        raise ValueError(
            "Azure Receipt OCR failed and OpenAI fallback also failed. "
            f"Azure: {azure_error}; OpenAI: {openai_error}"
        ) from openai_error
'''
        text = text.replace(marker, helper + marker, 1)

    old_config_variants = [
        """    provider = AzureReceiptOCRProvider()

    if not provider.is_configured():
        raise ValueError(
            "Azure Receipt OCR provider is not configured. "
            "Check AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )
""",
        """    provider = AzureReceiptOCRProvider()

    if not provider.is_configured():
        raise ValueError(
            "Azure Receipt OCR provider is not configured. "
            "Check AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
            "AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )
""",
    ]

    new_config = """    provider = AzureReceiptOCRProvider()

    if not provider.is_configured():
        azure_error = (
            "Azure Receipt OCR provider is not configured. "
            "Check AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and "
            "AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )

        if _openai_receipt_fallback_enabled():
            return _run_openai_receipt_fallback(
                db=db,
                document_id=document_id,
                azure_error=azure_error,
            )

        raise ValueError(azure_error)
"""

    if "azure_error = (" not in text:
        replaced = False
        for old_config in old_config_variants:
            if old_config in text:
                text = text.replace(old_config, new_config, 1)
                replaced = True
                break

        if not replaced and "if not provider.is_configured():" in text:
            raise RuntimeError(
                f"Azure provider block in {path} differs from the supported versions. "
                "No unsafe automatic replacement was attempted."
            )

    old_except = '''    except Exception as error:
        external_request.provider_status = "failed"
        external_request.error_message = str(error)

        db.commit()

        raise ValueError(f"Azure Receipt OCR failed: {error}")
'''
    new_except = '''    except Exception as error:
        external_request.provider_status = "failed"
        external_request.error_message = str(error)

        db.commit()

        if _openai_receipt_fallback_enabled():
            return _run_openai_receipt_fallback(
                db=db,
                document_id=document_id,
                azure_error=error,
            )

        raise ValueError(f"Azure Receipt OCR failed: {error}")
'''
    if old_except in text:
        text = text.replace(old_except, new_except, 1)
    elif "return _run_openai_receipt_fallback(" not in text[text.rfind("except Exception as error:"):]:
        raise RuntimeError(
            f"Final Azure exception block in {path} differs from the supported version."
        )

    path.write_text(text, encoding="utf-8")
    print(f"[PATCHED] {path}: Azure -> OpenAI OCR fallback enabled.")


def patch_translation(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    backup(path)
    text = path.read_text(encoding="utf-8")

    import_line = (
        "from app.services.openai_translation_service import "
        "translate_receipt_item_names_with_openai\n"
    )
    if import_line not in text:
        marker = "import requests\n"
        if marker not in text:
            raise RuntimeError(f"Could not find requests import in {path}.")
        text = text.replace(marker, marker + "\n" + import_line, 1)

    if "def _openai_translation_fallback_enabled" not in text:
        marker = "\ndef detect_receipt_language"
        if marker not in text:
            raise RuntimeError(
                f"Could not find detect_receipt_language() anchor in {path}."
            )
        helper = '''


def _openai_translation_fallback_enabled() -> bool:
    return os.getenv(
        "OPENAI_TRANSLATION_FALLBACK_ENABLED",
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}


def _run_openai_translation_fallback(
    item_names: list[str],
    azure_error: Exception | str | None = None,
) -> ReceiptTranslationResult:
    try:
        outcome = translate_receipt_item_names_with_openai(item_names)
        return ReceiptTranslationResult(
            source_language=outcome.source_language,
            translated_names=outcome.translated_names,
            skipped=outcome.skipped,
            error=outcome.error,
        )
    except Exception as openai_error:
        parts = []
        if azure_error:
            parts.append(f"Azure Translator: {azure_error}")
        parts.append(f"OpenAI translation fallback: {openai_error}")
        return ReceiptTranslationResult(
            skipped=True,
            error="; ".join(parts),
        )
'''
        text = text.replace(marker, helper + marker, 1)

    old_missing_key = '''    if not os.getenv("AZURE_TRANSLATOR_KEY"):
        return ReceiptTranslationResult(
            skipped=True,
            error="Azure Translator is not configured."
        )
'''
    new_missing_key = '''    if not os.getenv("AZURE_TRANSLATOR_KEY"):
        if _openai_translation_fallback_enabled():
            return _run_openai_translation_fallback(
                item_names=item_names,
                azure_error="Azure Translator is not configured.",
            )

        return ReceiptTranslationResult(
            skipped=True,
            error="Azure Translator is not configured."
        )
'''
    if old_missing_key in text:
        text = text.replace(old_missing_key, new_missing_key, 1)
    elif "if not os.getenv(\"AZURE_TRANSLATOR_KEY\")" in text and (
        "azure_error=\"Azure Translator is not configured.\"" not in text
    ):
        raise RuntimeError(
            f"Azure Translator missing-key block in {path} differs from supported version."
        )

    old_except = '''    except Exception as error:
        # Translation must never make receipt OCR fail.
        return ReceiptTranslationResult(
            skipped=True,
            error=str(error),
        )
'''
    new_except = '''    except Exception as error:
        # Translation must never make receipt OCR fail.
        if _openai_translation_fallback_enabled():
            return _run_openai_translation_fallback(
                item_names=item_names,
                azure_error=error,
            )

        return ReceiptTranslationResult(
            skipped=True,
            error=str(error),
        )
'''
    if old_except in text:
        text = text.replace(old_except, new_except, 1)
    elif "azure_error=error" not in text[text.rfind("except Exception as error:"):]:
        raise RuntimeError(
            f"Final Azure Translator exception block in {path} differs from supported version."
        )

    path.write_text(text, encoding="utf-8")
    print(f"[PATCHED] {path}: Azure Translator -> OpenAI fallback enabled.")


def main() -> None:
    backend_root = Path(__file__).resolve().parent.parent
    print("Pruvs v6.7 OpenAI fallback patch")
    print(f"Backend root: {backend_root}")

    patch_requirements(backend_root / "requirements.txt")
    patch_azure_direct(
        backend_root / "app/services/azure_receipt_direct_service.py"
    )
    patch_translation(
        backend_root / "app/services/receipt_translation_service.py"
    )

    print("\nPatch complete.")
    print(f"Backups use suffix {BACKUP_SUFFIX}.")
    print("Next: install requirements, set Render env vars, commit and redeploy.")


if __name__ == "__main__":
    main()
