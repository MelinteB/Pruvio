"""Only hashed, time-limited customer-issued codes are stored."""
from sqlalchemy import String,ForeignKey,DateTime
from sqlalchemy.orm import Mapped,mapped_column
from datetime import datetime
from .db import Base
from .models import utcnow
class CustomerClaimCode(Base):
    __tablename__='loyalty_customer_claim_codes_v12'
    claim_id: Mapped[str] = mapped_column(ForeignKey('receipt_claims.id'),primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'),nullable=False,index=True)
    code_hash: Mapped[str] = mapped_column(String(64),nullable=False,unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    unlocked_by_staff: Mapped[str | None] = mapped_column(ForeignKey('merchant_staff.id'),nullable=True)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
