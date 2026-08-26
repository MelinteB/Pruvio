from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean

from app.db.database import Base


class ExternalOCRUsage(Base):
    __tablename__ = "external_ocr_usage"

    id = Column(Integer, primary_key=True, index=True)

    external_ocr_request_id = Column(
        Integer,
        ForeignKey("external_ocr_requests.id"),
        nullable=False,
        index=True
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id"),
        nullable=False,
        index=True
    )

    case_id = Column(
        Integer,
        ForeignKey("cases.id"),
        nullable=False,
        index=True
    )

    provider = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)

    pages_processed = Column(Integer, default=1)
    items_count = Column(Integer, default=0)

    receipt_total = Column(Float, nullable=True)
    provider_confidence = Column(Float, nullable=True)
    validation_is_valid = Column(Boolean, nullable=True)

    duration_ms = Column(Integer, nullable=True)
    error_message = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)