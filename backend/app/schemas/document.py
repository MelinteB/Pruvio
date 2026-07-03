from datetime import datetime
from pydantic import BaseModel, ConfigDict

class DocumentOCRResponse(BaseModel):
    document_id: int
    ocr_text: str
    classification: dict
    
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    document_type: str
    original_filename: str | None = None
    stored_filename: str
    path: str
    mime_type: str | None = None
    size_bytes: int | None = None
    ocr_text: str | None = None
    created_at: datetime

class DocumentClassificationResponse(BaseModel):
    document_id: int
    document_type: str
    suggested_module: str
    confidence: float
    reason: str


class TextClassificationRequest(BaseModel):
    text: str