"""Audit trail for merchant-attested discounts (not POS/bank settlement confirmation)."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, utcnow

class DiscountRedemption(Base):
    __tablename__='loyalty_discount_reconciliation_v067'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    reward_id:Mapped[str]=mapped_column(ForeignKey('loyalty_rewards.id'),nullable=False,unique=True,index=True)
    merchant_id:Mapped[str]=mapped_column(ForeignKey('merchants.id'),nullable=False,index=True)
    program_id:Mapped[str]=mapped_column(ForeignKey('loyalty_programs.id'),nullable=False)
    source_claim_id:Mapped[str|None]=mapped_column(ForeignKey('receipt_claims.id'),nullable=True)
    consumer_id:Mapped[str]=mapped_column(String(100),nullable=False,index=True)
    staff_id:Mapped[str]=mapped_column(ForeignKey('merchant_staff.id'),nullable=False)
    sale_reference:Mapped[str]=mapped_column(String(120),nullable=False)
    sale_amount_minor:Mapped[int]=mapped_column(Integer,nullable=False)
    discount_minor:Mapped[int]=mapped_column(Integer,nullable=False)
    currency:Mapped[str]=mapped_column(String(3),nullable=False)
    verification_source:Mapped[str]=mapped_column(String(32),nullable=False,default='merchant_attested')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
