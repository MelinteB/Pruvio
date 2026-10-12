"""One exact upload fingerprint per user, retained across restarts."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.db.database import Base


class ReceiptFingerprint(Base):
    __tablename__ = 'receipt_fingerprints'
    __table_args__ = (UniqueConstraint('user_id', 'sha256', name='uq_receipt_fingerprint_user_sha'),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey('cases.id'), nullable=False, index=True)
    sha256 = Column(String(64), nullable=False)
    image_signature = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
