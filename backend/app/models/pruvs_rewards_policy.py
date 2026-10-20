"""Admin-managed referral rewards; immutable per-award OCR grant ledger."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String
from app.db.database import Base
class PruvsRewardPolicy(Base):
    __tablename__='pruvs_referral_reward_policy'
    id=Column(Integer,primary_key=True,default=1)
    pc_reward=Column(Integer,nullable=False,default=5)
    ocr_bonus=Column(Integer,nullable=False,default=2)
    version=Column(Integer,nullable=False,default=1)
    updated_by=Column(Integer)
    updated_at=Column(DateTime,default=datetime.utcnow)
class PruvsOCRBonusGrant(Base):
    __tablename__='pruvs_ocr_bonus_grants'
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    amount=Column(Integer,nullable=False)
    reference=Column(String(150),unique=True,nullable=False)
    created_at=Column(DateTime,default=datetime.utcnow)
