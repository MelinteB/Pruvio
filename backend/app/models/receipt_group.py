"""Owner-scoped receipt folders; moving a receipt never modifies OCR or split rows."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index
from app.db.database import Base

class ReceiptGroup(Base):
    __tablename__ = 'receipt_groups'
    id = Column(Integer, primary_key=True)
    owner_user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('owner_user_id', 'name', name='uq_receipt_group_owner_name'),)

class ReceiptGroupMembership(Base):
    __tablename__ = 'receipt_group_memberships'
    # Exactly one optional folder per receipt; no changes to existing cases/OCR data.
    case_id = Column(Integer, ForeignKey('cases.id', ondelete='CASCADE'), primary_key=True)
    group_id = Column(Integer, ForeignKey('receipt_groups.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
