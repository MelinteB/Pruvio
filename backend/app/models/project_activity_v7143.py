"""Additive project settings, original-currency expense allocations and member chat.

No existing source bill is mutated by project expense or settlement records.
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from app.db.database import Base


class ProjectOptions(Base):
    __tablename__ = 'project_options_v7143'
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), primary_key=True)
    smart_settle = Column(Boolean, nullable=False, default=True)
    primary_currency = Column(String(10), nullable=False, default='RON')


class ProjectManualBill(Base):
    __tablename__ = 'project_manual_bills_v7143'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    paid_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    merchant = Column(String(150), nullable=False)
    amount_minor = Column(Integer, nullable=False)
    currency = Column(String(10), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProjectExpenseShare(Base):
    """Allocations for manual bills or receipt-only imports; split sources own their allocations."""
    __tablename__ = 'project_expense_shares_v7143'
    __table_args__ = (UniqueConstraint('project_id','kind','source_id','user_id',name='uq_project_expense_share_v7143'),)
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(12), nullable=False)   # manual | receipt
    source_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    paid_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    amount_minor = Column(Integer, nullable=False)
    payment_status = Column(String(12), nullable=False, default='unpaid')  # unpaid|reported|confirmed
    reported_at = Column(DateTime)
    confirmed_at = Column(DateTime)


class ProjectChatMessage(Base):
    __tablename__ = 'project_chat_messages_v7143'
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('bill_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
