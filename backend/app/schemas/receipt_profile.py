from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ReceiptProfileCreate(BaseModel):
    merchant_name: str | None = None
    merchant_tax_id: str | None = None
    country: str = "RO"
    profile_name: str
    profile_signature: str | None = None
    parser_strategy: str = "generic"
    rules_json: str | None = None
    status: str = "draft"
    confidence_score: float = 0.0


class ReceiptProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_name: str | None = None
    merchant_tax_id: str | None = None
    country: str
    profile_name: str
    profile_signature: str | None = None
    parser_strategy: str
    rules_json: str | None = None
    status: str
    confidence_score: float
    success_count: int
    failure_count: int
    created_at: datetime
    updated_at: datetime


class ReceiptCorrectionCreate(BaseModel):
    case_id: int
    document_id: int
    wrong_extraction_json: str | None = None
    corrected_items_json: str
    notes: str | None = None


class ReceiptCorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    document_id: int
    correction_type: str
    original_ocr_text: str | None = None
    wrong_extraction_json: str | None = None
    corrected_items_json: str
    notes: str | None = None
    created_at: datetime