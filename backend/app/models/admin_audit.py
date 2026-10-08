from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.db.database import Base


class AdminAudit(Base):
    __tablename__ = "admin_audit"
    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, nullable=True, index=True)
    source = Column(String(30), nullable=False)
    action = Column(String(30), nullable=False)
    entity = Column(String(100), nullable=False)
    record_id = Column(Integer, nullable=True)
    changed_fields = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
