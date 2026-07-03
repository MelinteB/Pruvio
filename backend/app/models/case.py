from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    module: Mapped[str] = mapped_column(String(100), default="unknown")
    status: Mapped[str] = mapped_column(String(100), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="cases")
    documents = relationship("Document", back_populates="case")
    messages = relationship("Message", back_populates="case")
    reminders = relationship("Reminder", back_populates="case")
    receipt_items = relationship("ReceiptItem", back_populates="case")