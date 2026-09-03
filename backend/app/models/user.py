from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50),default="pending_join")
    accepted_terms: Mapped[bool] = mapped_column(Boolean,default=False)
    accepted_terms_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cases = relationship("Case", back_populates="user")
    email = Column(String, nullable=True, index=True)
    is_phone_verified = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)