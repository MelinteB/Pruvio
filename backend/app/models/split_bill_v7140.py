"""Additive state for exact-cent allocation modes and shared receipt lines."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from app.db.database import Base

class SplitAllocationState(Base):
    __tablename__ = 'split_allocation_states'
    session_id = Column(Integer, ForeignKey('split_bill_sessions.id', ondelete='CASCADE'), primary_key=True)
    mode = Column(String(20), nullable=False, default='items')
    revision = Column(Integer, nullable=False, default=0)
    # Original manual assignments are persisted until switching back from equal mode.
    snapshot_json = Column(Text, nullable=True)
    modified_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class SplitSharedItem(Base):
    __tablename__ = 'split_shared_items'
    session_id = Column(Integer, ForeignKey('split_bill_sessions.id', ondelete='CASCADE'), primary_key=True)
    receipt_item_id = Column(Integer, ForeignKey('receipt_items.id', ondelete='CASCADE'), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
