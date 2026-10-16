"""Pruvs subscription catalogue, Stripe reconciliation and invoice email outbox.

Does not store card data, Stripe secrets, or merchant loyalty points.
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from app.db.database import Base


class PruvsPlanConfig(Base):
    __tablename__ = 'pruvs_plan_catalog'
    key = Column(String(24), primary_key=True)
    price_minor = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default='eur')
    interval = Column(String(12), nullable=False, default='month')
    interval_count = Column(Integer, nullable=False, default=1)
    ocr_allowance = Column(Integer, nullable=False)
    expense_reports = Column(Integer, nullable=False)
    description = Column(Text, nullable=False, default='')
    features_json = Column(Text, nullable=False, default='[]')
    stripe_product_id = Column(String(128), nullable=True)
    stripe_price_id = Column(String(128), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PruvsStripeAccount(Base):
    __tablename__ = 'pruvs_stripe_accounts'
    user_id = Column(Integer, primary_key=True)
    customer_id = Column(String(128), unique=True, nullable=True)
    subscription_id = Column(String(128), unique=True, nullable=True)
    price_id = Column(String(128), nullable=True)
    plan = Column(String(24), nullable=True)
    status = Column(String(32), nullable=False, default='none')
    paid_at = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PruvsStripeCheckout(Base):
    __tablename__ = 'pruvs_stripe_checkouts'
    session_id = Column(String(160), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    plan = Column(String(24), nullable=False)
    price_id = Column(String(128), nullable=False)
    customer_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PruvsStripeEvent(Base):
    __tablename__ = 'pruvs_stripe_events'
    event_id = Column(String(160), primary_key=True)
    event_type = Column(String(100), nullable=False)
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PruvsInvoiceEmail(Base):
    __tablename__ = 'pruvs_invoice_emails'
    invoice_id = Column(String(128), primary_key=True)
    user_id = Column(Integer, nullable=False)
    email = Column(String(320), nullable=False)
    hosted_invoice_url = Column(Text, nullable=True)
    state = Column(String(20), nullable=False, default='pending')
    attempts = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)

class PruvsCreditCostConfig(Base):
    __tablename__ = 'pruvs_credit_cost_config'
    id = Column(Integer, primary_key=True, default=1)
    ocr_pc = Column(Integer, nullable=False, default=2)
    report_pc = Column(Integer, nullable=False, default=5)
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(Integer, nullable=True)
