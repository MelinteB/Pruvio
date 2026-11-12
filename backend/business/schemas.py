from pydantic import BaseModel, Field
from typing import Literal

class LoginIn(BaseModel):
    email: str
    password: str

class StoreIn(BaseModel):
    name: str = Field(min_length=2,max_length=180)
    address: str = Field(default='',max_length=250)
    latitude: float = Field(ge=-90,le=90)
    longitude: float = Field(ge=-180,le=180)

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
