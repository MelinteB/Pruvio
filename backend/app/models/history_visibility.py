"""Per-user history organization; underlying receipts and shared bills remain intact."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from app.db.database import Base


class HistoryVisibility(Base):
    __tablename__ = 'pruvs_history_visibility'
    __table_args__ = (UniqueConstraint('user_id', 'kind', 'source_id', name='uq_pruvs_history_item'),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    kind = Column(String(12), nullable=False)
    source_id = Column(Integer, nullable=False)
    state = Column(String(12), nullable=False, default='active')
    note = Column(String(300), nullable=False, default='')
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
