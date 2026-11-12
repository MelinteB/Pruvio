import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, UniqueConstraint, DateTime, Integer, Float, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid(): return str(uuid.uuid4())
def utcnow(): return datetime.now(timezone.utc)

class Merchant(Base):
    __tablename__='merchants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='active', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Staff(Base):
    __tablename__='merchant_staff'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default='owner')
    active: Mapped[bool] = mapped_column(default=True)

class Store(Base):
    __tablename__='stores'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), index=True)
    name: Mapped[str] = mapped_column(String(180))
    address: Mapped[str] = mapped_column(String(250), default='')
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(default=True)

class Program(Base):
    __tablename__='loyalty_programs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), index=True)
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(String(500), default='')
    stamps_required: Mapped[int] = mapped_column(Integer)
    min_purchase_minor: Mapped[int] = mapped_column(Integer, default=0)
    reward_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default='RON')
    status: Mapped[str] = mapped_column(String(20), default='draft')

class Membership(Base):
    __tablename__='loyalty_memberships'
    __table_args__=(UniqueConstraint('consumer_id','program_id',name='uq_consumer_program'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    consumer_id: Mapped[str] = mapped_column(String(100), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey('loyalty_programs.id'), index=True)
    stamps: Mapped[int] = mapped_column(Integer, default=0)

class ReceiptClaim(Base):
    __tablename__='receipt_claims'
    __table_args__=(UniqueConstraint('source_system','external_receipt_id',name='uq_source_receipt'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey('loyalty_programs.id'), index=True)
    consumer_id: Mapped[str] = mapped_column(String(100), index=True)
    source_system: Mapped[str] = mapped_column(String(30), default='pruvs')
    external_receipt_id: Mapped[str] = mapped_column(String(100))
    amount_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Reward(Base):
    __tablename__='loyalty_rewards'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey('loyalty_programs.id'), index=True)
    consumer_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default='available')
    redemption_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_claim_id: Mapped[str | None] = mapped_column(ForeignKey('receipt_claims.id'),nullable=True,index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Campaign(Base):
    __tablename__='merchant_campaigns'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), index=True)
    title: Mapped[str] = mapped_column(String(180))
    goal: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='draft')
    generator: Mapped[str] = mapped_column(String(30), default='manual')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

Index('ix_reward_consumer_status', Reward.consumer_id, Reward.status)
class Promotion(Base):
    """Merchant-approved display creative for exactly one published loyalty program."""
    __tablename__='loyalty_promotions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), nullable=False, index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey('loyalty_programs.id'), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='draft')
    media_url: Mapped[str | None] = mapped_column(String(900), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    media_alt: Mapped[str | None] = mapped_column(String(160), nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class PurchaseCode(Base):
    """A merchant-issued proof of a completed checkout; claim may still be rejected."""
    __tablename__='loyalty_purchase_codes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey('merchants.id'), nullable=False, index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey('loyalty_programs.id'), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_id: Mapped[str | None] = mapped_column(ForeignKey('receipt_claims.id'), unique=True, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
