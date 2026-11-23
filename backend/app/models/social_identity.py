"""Trusted external OAuth identities; never match accounts by unverified email."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from app.db.database import Base

class SocialAccount(Base):
    __tablename__ = 'pruvs_social_accounts'
    __table_args__ = (
        UniqueConstraint('provider', 'subject', name='uq_pruvs_social_provider_subject'),
        UniqueConstraint('user_id', 'provider', name='uq_pruvs_social_user_provider'),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    subject = Column(String(255), nullable=False)
    display_name = Column(String(255))
    connected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime)
