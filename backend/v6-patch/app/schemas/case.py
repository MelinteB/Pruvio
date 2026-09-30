from datetime import datetime
from pydantic import BaseModel, ConfigDict


class CaseCreate(BaseModel):
    user_id: int
    module: str = "unknown"
    status: str = "created"


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    module: str
    status: str
    created_at: datetime

class CaseDetailResponse(CaseResponse):
    pass