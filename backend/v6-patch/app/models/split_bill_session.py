from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float

from app.db.database import Base


class SplitBillSession(Base):
    __tablename__ = "split_bill_sessions"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="open", index=True)
    currency = Column(String, default="RON")
    expected_participants_count = Column(Integer, nullable=False, default=2)

    # Tip is set by the owner and shared equally by everyone in the session,
    # including the owner. tip_mode: none | percent | fixed.
    tip_mode = Column(String(20), nullable=False, default="none")
    tip_value = Column(Float, nullable=False, default=0.0)

    closed_at = Column(DateTime, nullable=True)  # legacy compatibility
    settled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=7))
