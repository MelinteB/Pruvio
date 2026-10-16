"""Server-side subscription usage and manual upgrade requests. No stored-money ledger."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Index
from app.db.database import Base

class PruvsMeteredUse(Base):
    __tablename__ = 'pruvs_metered_uses'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    resource = Column(String(32), nullable=False)
    month = Column(String(7), nullable=False)
    state = Column(String(16), nullable=False, default='reserved')
    paid_with = Column(String(16), nullable=False, default='allowance')
    credit_cost = Column(Integer, nullable=False, default=0)
    token = Column(String(80), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    __table_args__ = (Index('ix_pruvs_use_user_month_resource', 'user_id', 'month', 'resource'),)

class PruvsUpgradeRequest(Base):
    __tablename__ = 'pruvs_upgrade_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    requested_plan = Column(String(24), nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, nullable=True)
