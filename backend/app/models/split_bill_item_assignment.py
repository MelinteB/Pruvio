from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Float

from app.db.database import Base


class SplitBillItemAssignment(Base):
    __tablename__ = "split_bill_item_assignments"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        Integer,
        ForeignKey("split_bill_sessions.id"),
        nullable=False,
        index=True
    )

    participant_id = Column(
        Integer,
        ForeignKey("split_bill_participants.id"),
        nullable=False,
        index=True
    )

    receipt_item_id = Column(
        Integer,
        ForeignKey("receipt_items.id"),
        nullable=False,
        index=True
    )

    amount = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)