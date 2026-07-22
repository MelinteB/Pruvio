from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ExternalOCRRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    case_id: int
    reason: str
    provider_status: str
    preferred_provider: str | None = None
    local_confidence: float | None = None
    local_name_quality: float | None = None
    local_detected_total: float | None = None
    local_receipt_total: float | None = None
    external_result_json: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

class ExternalOCRMockItem(BaseModel):
    name: str
    quantity: float = 1.0
    unit_price: float | None = None
    total_price: float
    currency: str = "RON"


class ExternalOCRMockResult(BaseModel):
    provider: str = "mock_external_ocr"
    merchant_name: str | None = None
    receipt_total: float
    currency: str = "RON"
    provider_confidence: float = 0.90
    items: list[ExternalOCRMockItem]