"""Auditable user-reported payment and bill-owner acknowledgment events.

Never indicates verified bank settlement. Records are scoped to the split session.
"""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, Numeric, String, Index
from app.db.database import Base


class PaymentConfirmationEvent(Base):
    __tablename__ = 'pruvs_payment_confirmation_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    participant_id = Column(Integer, nullable=False, index=True)
    actor_user_id = Column(Integer, nullable=False)
    event_type = Column(String(32), nullable=False)
    method = Column(String(40), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(12), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (Index('ix_pruvs_payment_audit_session_time', 'session_id', 'created_at'),)
