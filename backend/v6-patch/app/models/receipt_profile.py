from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ReceiptProfile(Base):
    __tablename__ = "receipt_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    merchant_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    merchant_tax_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )

    country: Mapped[str] = mapped_column(
        String(10),
        default="RO"
    )

    profile_name: Mapped[str] = mapped_column(
        String(255),
        default="unknown_receipt_profile"
    )

    profile_signature: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )
    # JSON string with keywords/signature markers

    parser_strategy: Mapped[str] = mapped_column(
        String(100),
        default="generic"
    )
    # examples:
    # generic
    # quantity_before_product
    # product_price_same_line
    # product_price_next_line

    rules_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="draft"
    )
    # draft
    # candidate
    # active
    # disabled
    # rejected

    confidence_score: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    success_count: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    failure_count: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )