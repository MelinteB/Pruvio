"""Staging-only opt-in merchant receipt-pilot enrollment and audit history."""
from sqlalchemy import String, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base
from .models import uid, utcnow


class MerchantPilotEnrollment(Base):
    __tablename__ = 'merchant_pilot_enrollment_v0612'

    merchant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('merchants.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='requested')
    requested_by_staff_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('merchant_staff.id'), nullable=True)
    reviewed_by_staff_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('merchant_staff.id'), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False)


class MerchantPilotAudit(Base):
    __tablename__ = 'merchant_pilot_audit_v0612'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('merchants.id'), nullable=False, index=True)
    actor_staff_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('merchant_staff.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    old_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False)
