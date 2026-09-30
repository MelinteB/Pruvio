from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ReceiptCorrection(Base):
    __tablename__ = "receipt_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id"),
        index=True
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"),
        index=True
    )

    correction_type: Mapped[str] = mapped_column(
        String(100),
        default="manual"
    )
    # manual
    # ai_suggested
    # admin_reviewed

    original_ocr_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    wrong_extraction_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    corrected_items_json: Mapped[str] = mapped_column(
        Text
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )