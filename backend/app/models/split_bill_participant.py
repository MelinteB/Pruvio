from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.db.database import Base


class SplitBillParticipant(Base):
    __tablename__ = "split_bill_participants"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        Integer,
        ForeignKey("split_bill_sessions.id"),
        nullable=False,
        index=True
    )

    display_name = Column(String, nullable=False)
    participant_token = Column(String, unique=True, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)