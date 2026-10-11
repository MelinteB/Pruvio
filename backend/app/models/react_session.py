from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from app.db.database import Base

class ReactSession(Base):
    __tablename__ = 'pruvs_react_sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    csrf_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

class ReactChallenge(Base):
    __tablename__ = 'pruvs_react_challenges'
    id = Column(String(64), primary_key=True)
    purpose = Column(String(30), nullable=False)
    user_id = Column(Integer, nullable=True)
    challenge = Column(Text, nullable=False)
    binding_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)

class ReactRateLimit(Base):
    __tablename__ = 'pruvs_react_rate_limits'
    id = Column(String(64), primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    reset_at = Column(DateTime, nullable=False)
