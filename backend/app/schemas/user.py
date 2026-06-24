from datetime import datetime
from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    phone_number: str
    name: str | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone_number: str
    name: str | None = None
    status: str
    accepted_terms: bool
    created_at: datetime