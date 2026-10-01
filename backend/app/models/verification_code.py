from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.db.database import Base


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    destination_type = Column(String, nullable=False, index=True)
    destination = Column(String, nullable=False, index=True)

    purpose = Column(String, default="onboarding", index=True)

    code_hash = Column(String, nullable=False)
    challenge_id = Column(String(64), nullable=True, index=True)
    context_value = Column(String(255), nullable=True)
    code_ciphertext = Column(String, nullable=True)
    provider_message_id = Column(String(255), nullable=True, index=True)
    delivery_channel = Column(String(30), nullable=True)
    delivery_status = Column(String(30), nullable=True)
    fallback_at = Column(DateTime, nullable=True)

    status = Column(String, default="pending", index=True)

    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)

    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime, nullable=True)