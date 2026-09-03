from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.db.database import Base


class SplitBillSession(Base):
    __tablename__ = "split_bill_sessions"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(
        Integer,
        ForeignKey("cases.id"),
        nullable=False,
        index=True
    )

    owner_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )

    token = Column(String, unique=True, nullable=False, index=True)

    status = Column(String, default="open", index=True)
    currency = Column(String, default="RON")

    expected_participants_count = Column(
        Integer,
        nullable=False,
        default=2
    )

    closed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(days=7)
    )