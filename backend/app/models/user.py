from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.usernames import default_username, default_username_key


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, default=default_username)
    username_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False, default=default_username_key)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    revolut_payment_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_iban: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_bic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending_join")
    accepted_terms: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_terms_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    accepted_privacy: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_privacy_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    privacy_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    notifications_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_language: Mapped[str] = mapped_column(String(12), default="en")

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cases = relationship("Case", back_populates="user")
    passkeys = relationship("PasskeyCredential", back_populates="user", cascade="all, delete-orphan")
