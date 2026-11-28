"""Per-program receipt reward approval, scoped to the exact merchant location."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid, utcnow


class ProgramPilotEnrollment(Base):
    __tablename__ = 'merchant_program_pilot_enrollment_v0726'

    program_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('loyalty_programs.id'), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('merchants.id'), nullable=False, index=True)
    store_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('stores.id'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='requested')
    requested_by_staff_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('merchant_staff.id'), nullable=True)
    reviewed_by_staff_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('merchant_staff.id'), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProgramPilotAudit(Base):
    __tablename__ = 'merchant_program_pilot_audit_v0726'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    program_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('loyalty_programs.id'), nullable=False, index=True)
    merchant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('merchants.id'), nullable=False, index=True)
    store_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('stores.id'), nullable=False, index=True)
    actor_staff_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('merchant_staff.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    old_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
