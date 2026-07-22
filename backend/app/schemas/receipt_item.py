from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    document_id: int
    name: str
    quantity: float
    unit_price: float | None = None
    total_price: float
    currency: str
    selected_by_user: bool
    created_at: datetime


class ReceiptExtractionResponse(BaseModel):
    document_id: int
    case_id: int
    items_count: int
    detected_total: float
    receipt_total: float | None = None
    confidence: float
    name_quality: float
    external_ocr_request_id: int | None = None
    external_ocr_request_created: bool
    external_ocr_recommended: bool
    extraction_status: str
    recommended_next_step: str
    warnings: list[str]
    profile_id: int | None = None
    profile_name: str | None = None
    parser_strategy: str
    draft_profile_created: bool
    draft_profile_id: int | None = None
    items: list[ReceiptItemResponse]


class SplitBillCalculationRequest(BaseModel):
    tip_percent: float = 0
    service_charge: float = 0


class SplitBillCalculationResponse(BaseModel):
    case_id: int
    selected_items_count: int
    subtotal: float
    service_charge: float
    tip_percent: float
    tip_amount: float
    total_to_pay: float
    currency: str
    selected_items: list[ReceiptItemResponse]