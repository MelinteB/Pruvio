from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.db.database import Base


class SplitBillParticipant(Base):
    __tablename__ = "split_bill_participants"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("split_bill_sessions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    display_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=True, index=True)
    participant_token = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, default="participant", index=True)
    status = Column(String, default="joined", index=True)

    reminder_message = Column(String(500), nullable=True)
    reminder_at = Column(DateTime, nullable=True)

    payment_status = Column(String(30), nullable=False, default="unpaid")
    payment_method = Column(String(40), nullable=True)
    paid_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
