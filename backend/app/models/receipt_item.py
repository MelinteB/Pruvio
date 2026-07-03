from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id"),
        index=True
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"),
        index=True
    )

    name: Mapped[str] = mapped_column(String(255))

    quantity: Mapped[float] = mapped_column(
        Float,
        default=1.0
    )

    unit_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    total_price: Mapped[float] = mapped_column(Float)

    currency: Mapped[str] = mapped_column(
        String(10),
        default="RON"
    )

    selected_by_user: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    case = relationship("Case", back_populates="receipt_items")
    document = relationship("Document", back_populates="receipt_items")