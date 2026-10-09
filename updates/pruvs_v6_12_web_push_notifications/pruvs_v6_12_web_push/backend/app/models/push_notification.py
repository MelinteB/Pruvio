"""Additive notification tables; no existing business tables are altered."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from app.db.database import Base


class PushGrant(Base):
    __tablename__ = 'pruvs_push_grants'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class PushDevice(Base):
    __tablename__ = 'pruvs_push_devices'
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    grant_hash = Column(String(64), nullable=False, index=True)
    endpoint_hash = Column(String(64), unique=True, nullable=False)
    subscription = Column(Text, nullable=False)
    label = Column(String(120), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    test_hash = Column(String(64), nullable=True)
    test_expires_at = Column(DateTime, nullable=True)
    last_test_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PushPreference(Base):
    __tablename__ = 'pruvs_push_preferences'
    user_id = Column(Integer, primary_key=True)
    push_enabled = Column(Boolean, default=True, nullable=False)
    email_enabled = Column(Boolean, default=True, nullable=False)
    receipts = Column(Boolean, default=True, nullable=False)
    bills = Column(Boolean, default=True, nullable=False)
    reminders = Column(Boolean, default=True, nullable=False)


class PushEvent(Base):
    __tablename__ = 'pruvs_push_events'
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    title = Column(String(120), nullable=False)
    body = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False)
    device_id = Column(String(36), nullable=True)
    confirmation = Column(String(100), nullable=True)
    status = Column(String(30), default='pending', nullable=False, index=True)
    available_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    lease_until = Column(DateTime, nullable=True)
    lease_token = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    read_at = Column(DateTime, nullable=True)
    email_attempts = Column(Integer, default=0, nullable=False)
    email_status = Column(String(30), nullable=True)


class PushDelivery(Base):
    __tablename__ = 'pruvs_push_deliveries'
    id = Column(String(80), primary_key=True)
    event_id = Column(String(36), nullable=False, index=True)
    device_id = Column(String(36), nullable=False)
    status = Column(String(30), default='pending', nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    error_code = Column(String(60), nullable=True)
