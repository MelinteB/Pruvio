from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base



class ExternalOCRRequest(Base):
    __tablename__ = "external_ocr_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"),
        index=True
    )

    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id"),
        index=True
    )

    reason: Mapped[str] = mapped_column(
        String(255),
        default="local_ocr_quality_low"
    )

    provider_status: Mapped[str] = mapped_column(
        String(50),
        default="pending"
    )
    # pending
    # processing
    # completed
    # failed
    # needs_review
    # skipped

    preferred_provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )
    # azure_receipt
    # aws_textract
    # mindee
    # ai_vision

    local_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    local_name_quality: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    local_detected_total: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    local_receipt_total: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    external_result_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )