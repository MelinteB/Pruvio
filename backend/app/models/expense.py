"""User owned expense report profiles and immutable report snapshots."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from app.db.database import Base


class ExpenseCompany(Base):
    __tablename__ = 'pruvs_expense_companies'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String(180), nullable=False)
    tax_id = Column(String(80), nullable=False, default='')
    registration_number = Column(String(80), nullable=False, default='')
    vat_number = Column(String(80), nullable=False, default='')
    address = Column(String(500), nullable=False, default='')
    country = Column(String(100), nullable=False, default='')
    department = Column(String(120), nullable=False, default='')
    cost_center = Column(String(120), nullable=False, default='')
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExpenseReport(Base):
    __tablename__ = 'pruvs_expense_reports'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    company_id = Column(Integer, nullable=True)
    title = Column(String(180), nullable=False)
    snapshot_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
