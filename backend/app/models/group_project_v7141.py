"""Additive, access-controlled shared projects containing saved receipts and split sessions."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from app.db.database import Base

class BillProject(Base):
    __tablename__ = 'bill_projects'
    id = Column(Integer, primary_key=True)
    owner_user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    modified_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class BillProjectItem(Base):
    __tablename__ = 'bill_project_items'
    __table_args__ = (UniqueConstraint('project_id', 'kind', 'source_id', name='uq_bill_project_item'),)
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    added_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(12), nullable=False)  # receipt (case_id) | split (session_id)
    source_id = Column(Integer, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class BillProjectMember(Base):
    __tablename__ = 'bill_project_members'
    __table_args__ = (UniqueConstraint('project_id', 'user_id', name='uq_bill_project_member'),)
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    status = Column(String(16), nullable=False, default='invited')  # owner / invited / joined
    # Optional participant-selected payment destination. Never auto-share private profiles.
    payment_profile_id = Column(Integer, ForeignKey('payment_profiles.id', ondelete='SET NULL'), nullable=True)
    invited_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    joined_at = Column(DateTime, nullable=True)
