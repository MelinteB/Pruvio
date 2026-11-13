"""Consent-limited merchant receipt review evidence and auditable preview events.

No receipt is publicly addressable. Evidence snapshots are only displayed to
merchant staff after authentication and per-merchant claim ownership checks.
"""
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Integer, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import utcnow, uid

class ReceiptEvidence(Base):
    __tablename__ = 'loyalty_receipt_evidence'
    claim_id: Mapped[str] = mapped_column(ForeignKey('receipt_claims.id'), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), nullable=False, index=True)
    merchant_label: Mapped[str] = mapped_column(String(160), nullable=False)
    receipt_date: Mapped[str] = mapped_column(String(32), nullable=False, default='')
    image_jpeg: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rejection_reason: Mapped[str] = mapped_column(String(300), nullable=False, default='')
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class ReceiptEvidenceAccess(Base):
    __tablename__ = 'loyalty_receipt_evidence_access'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    claim_id: Mapped[str] = mapped_column(ForeignKey('receipt_claims.id'), nullable=False, index=True)
    staff_id: Mapped[str] = mapped_column(ForeignKey('merchant_staff.id'), nullable=False)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
