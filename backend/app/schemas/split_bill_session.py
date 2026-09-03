from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SplitBillSessionCreateResponse(BaseModel):
    session_id: int
    case_id: int
    token: str
    status: str
    share_url: str
    qr_url: str
    created_at: datetime
    expires_at: datetime


class SplitBillParticipantCreate(BaseModel):
    display_name: str


class SplitBillParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    display_name: str
    participant_token: str
    created_at: datetime


class SplitBillSessionSelectionRequest(BaseModel):
    participant_id: int
    selected_item_ids: list[int]
    tip_percent: float = 0
    service_charge: float = 0


class SplitBillSessionSummaryResponse(BaseModel):
    session_id: int
    case_id: int
    token: str
    status: str
    bill_total: float
    assigned_total: float
    remaining_total: float
    currency: str
    participants: list[dict]
    items: list[dict]
    share_url: str
    qr_url: str