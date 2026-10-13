"""Reusable payment destination owned by a user."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from app.db.database import Base


class PaymentProfile(Base):
    __tablename__ = 'payment_profiles'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    recipient_name = Column(String(255), nullable=False)
    iban = Column(String(64), nullable=True)
    bank_name = Column(String(255), nullable=True)
    bic = Column(String(32), nullable=True)
    revolut_link = Column(String(500), nullable=True)
    payment_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
