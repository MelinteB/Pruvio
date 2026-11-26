from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=256)

class StoreIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=180)]
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=250)] = ''
    latitude: float = Field(ge=-90,le=90)
    longitude: float = Field(ge=-180,le=180)
    google_place_id: str | None = Field(default=None, min_length=8, max_length=255)

class StoreUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=180)]
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=250)] = ''
    latitude: float = Field(ge=-90,le=90)
    longitude: float = Field(ge=-180,le=180)
    active: bool = True

class ProgramIn(BaseModel):
    store_id: str
    title: str = Field(min_length=3,max_length=180)
    description: str = Field(default='',max_length=500)
    stamps_required: int = Field(ge=2,le=30)
    min_purchase_minor: int = Field(default=0,ge=0,le=10000000)
    reward_minor: int = Field(ge=1,le=10000000)
    currency: Literal['RON'] = 'RON'

class CampaignGoal(BaseModel):
    goal: str = Field(min_length=8,max_length=300)

class CampaignIn(BaseModel):
    title: str = Field(min_length=3,max_length=180)
    goal: str = Field(min_length=8,max_length=300)
    message: str = Field(min_length=5,max_length=2000)

class ReceiptProofIn(BaseModel):
    program_id: str
    receipt_proof: str

class ConfirmIn(BaseModel):
    code: str = Field(min_length=8,max_length=32)

class DemoReceiptIn(BaseModel):
    program_id: str
    amount_minor: int = Field(ge=1,le=10000000)
