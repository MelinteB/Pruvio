from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"),index=True)
    document_type: Mapped[str] = mapped_column(String(100), default="unknown")
    # possible values:
    # receipt
    # invoice
    # screenshot
    # qr_code
    # pdf
    # payment_proof
    # unknown

    original_filename: Mapped[str | None] = mapped_column(String(255),nullable=True)
    stored_filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(100),nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer,nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text,nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow)
    case = relationship("Case", back_populates="documents")
    receipt_items = relationship("ReceiptItem", back_populates="document")