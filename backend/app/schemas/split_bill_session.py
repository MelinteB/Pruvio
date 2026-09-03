from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SplitBillSessionCreateRequest(BaseModel):
    owner_user_id: int
    expected_participants_count: int = Field(default=2, ge=1)


class SplitBillSessionCreateResponse(BaseModel):
    session_id: int
    case_id: int
    owner_user_id: int | None
    token: str
    status: str
    expected_participants_count: int
    joined_participants_count: int
    missing_participants_count: int
    can_close: bool
    close_block_reason: str | None = None
    share_url: str
    qr_url: str
    owner_widget_url: str | None = None
    created_at: datetime
    expires_at: datetime


class SplitBillJoinRequest(BaseModel):
    phone_number: str
    display_name: str | None = None


class SplitBillJoinResponse(BaseModel):
    status: str
    message: str
    user_status: str | None = None
    participant_id: int | None = None
    participant_token: str | None = None
    display_name: str | None = None
    widget_url: str | None = None


class SplitBillParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    user_id: int | None = None
    display_name: str
    phone_number: str | None = None
    participant_token: str
    role: str
    status: str
    created_at: datetime


class SplitBillSessionSelectionRequest(BaseModel):
    participant_id: int
    selected_item_ids: list[int]


class SplitBillSessionCloseRequest(BaseModel):
    owner_user_id: int


class SplitBillSessionSummaryResponse(BaseModel):
    session_id: int
    case_id: int
    owner_user_id: int | None
    token: str
    status: str

    expected_participants_count: int
    joined_participants_count: int
    missing_participants_count: int

    bill_total: float
    assigned_total: float
    remaining_total: float
    currency: str

    can_close: bool
    close_block_reason: str | None = None

    participants: list[dict]
    items: list[dict]

    share_url: str
    qr_url: str


class SplitBillCloseResponse(BaseModel):
    session_id: int
    status: str
    closed_at: datetime | None = None
    message: str