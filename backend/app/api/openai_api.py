import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.users import require_admin_api_key
from app.db.database import get_db


router = APIRouter(dependencies=[Depends(require_admin_api_key)])


class OpenAITranslationRequest(BaseModel):
    item_names: list[str] = Field(min_length=1, max_length=200)


@router.get("/status")
def openai_status():
    """Return OpenAI configuration status without exposing the API key."""
    receipt_model = os.getenv("OPENAI_RECEIPT_MODEL", "gpt-6-luna").strip()
    translation_model = os.getenv(
        "OPENAI_TRANSLATION_MODEL",
        receipt_model or "gpt-6-luna",
    ).strip()
    return {
        "configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "receipt_model": receipt_model,
        "translation_model": translation_model,
        "receipt_fallback_enabled": os.getenv(
            "OPENAI_RECEIPT_FALLBACK_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"},
        "translation_fallback_enabled": os.getenv(
            "OPENAI_TRANSLATION_FALLBACK_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"},
    }


@router.post("/receipts/{document_id}/process")
def process_receipt_with_openai(
    document_id: int,
    db: Session = Depends(get_db),
):
    """
    Process an existing Pruvs document directly with OpenAI receipt OCR.

    This admin-only endpoint is useful for validating the OpenAI integration
    independently of Azure and for controlled diagnostics. It does not expose
    the OpenAI API key.
    """
    try:
        from app.services.openai_receipt_direct_service import (
            process_document_with_openai_receipt_direct,
        )
        return process_document_with_openai_receipt_direct(
            db=db,
            document_id=document_id,
            reason="admin_openai_api",
            fallback_used=False,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"OpenAI receipt processing failed: {error}")


@router.post("/translate")
def translate_with_openai(payload: OpenAITranslationRequest):
    """Translate receipt item names directly with OpenAI (admin only)."""
    try:
        from app.services.openai_translation_service import (
            translate_receipt_item_names_with_openai,
        )
        outcome = translate_receipt_item_names_with_openai(payload.item_names)
        return {
            "source_language": outcome.source_language,
            "translated_names": outcome.translated_names,
            "skipped": outcome.skipped,
            "usage": outcome.usage,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"OpenAI translation failed: {error}")
