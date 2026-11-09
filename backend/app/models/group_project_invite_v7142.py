"""Short-lived, revocable invitation links for shared projects (no plaintext token stored)."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean
from app.db.database import Base

class BillProjectInvite(Base):
    __tablename__ = 'bill_project_invites'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), index=True, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    uses = Column(Integer, default=0, nullable=False)
    max_uses = Column(Integer, default=100, nullable=False)
