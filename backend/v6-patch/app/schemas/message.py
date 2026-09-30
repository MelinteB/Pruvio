from datetime import datetime
from pydantic import BaseModel, ConfigDict


class MessageCreate(BaseModel):
    case_id: int
    direction: str
    content: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    direction: str
    content: str | None = None
    created_at: datetime