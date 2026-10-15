"""Isolated Pruvs commerce demo ledger. No stored-money, merchant funds or card data."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean, UniqueConstraint, Index
from app.db.database import Base

class DemoSubscription(Base):
    __tablename__='pruvs_demo_subscriptions'
    user_id=Column(Integer,primary_key=True)
    plan=Column(String(20),nullable=False,default='free')
    status=Column(String(20),nullable=False,default='demo')
    activated_at=Column(DateTime,default=datetime.utcnow,nullable=False)
    expires_at=Column(DateTime,nullable=True)

class CreditEntry(Base):
    __tablename__='pruvs_credit_entries'
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    delta=Column(Integer,nullable=False)
    reason=Column(String(80),nullable=False)
    reference=Column(String(140),nullable=False,unique=True)
    created_at=Column(DateTime,default=datetime.utcnow,nullable=False)

class Referral(Base):
    __tablename__='pruvs_split_referrals'
    id=Column(Integer,primary_key=True)
    owner_id=Column(Integer,nullable=False,index=True)
    referred_id=Column(Integer,nullable=False,unique=True)
    session_id=Column(Integer,nullable=False)
    status=Column(String(20),default='pending',nullable=False)
    created_at=Column(DateTime,default=datetime.utcnow,nullable=False)
    rewarded_at=Column(DateTime,nullable=True)

class Merchant(Base):
    __tablename__='pruvs_reward_merchants'
    id=Column(Integer,primary_key=True)
    name=Column(String(160),nullable=False)
    tax_id=Column(String(40),nullable=True)
    created_at=Column(DateTime,default=datetime.utcnow,nullable=False)

class Campaign(Base):
    __tablename__='pruvs_reward_campaigns'
    id=Column(Integer,primary_key=True)
    merchant_id=Column(Integer,ForeignKey('pruvs_reward_merchants.id'),nullable=False,index=True)
    code=Column(String(40),nullable=False,unique=True)
    title=Column(String(180),nullable=False)
    threshold_minor=Column(Integer,nullable=False,default=5000)
    required_receipts=Column(Integer,nullable=False,default=3)
    voucher_minor=Column(Integer,nullable=False,default=2000)
    currency=Column(String(3),nullable=False,default='RON')
    active=Column(Boolean,nullable=False,default=True)
    demo_only=Column(Boolean,nullable=False,default=True)
    created_at=Column(DateTime,default=datetime.utcnow,nullable=False)

class ReceiptMark(Base):
    __tablename__='pruvs_reward_receipt_marks'
    id=Column(Integer,primary_key=True)
    case_id=Column(Integer,nullable=False,index=True)
    campaign_id=Column(Integer,ForeignKey('pruvs_reward_campaigns.id'),nullable=False)
    admin_id=Column(Integer,nullable=False)
    created_at=Column(DateTime,default=datetime.utcnow,nullable=False)
    __table_args__=(UniqueConstraint('case_id','campaign_id',name='uq_pruvs_demo_receipt_campaign'),)

class RewardClaim(Base):
    __tablename__='pruvs_reward_claims'
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    case_id=Column(Integer,nullable=False,index=True)
    campaign_id=Column(Integer,ForeignKey('pruvs_reward_campaigns.id'),nullable=False,index=True)
    status=Column(String(24),nullable=False,default='pending')
    reviewed_by=Column(Integer,nullable=True)
    created_at=Column(DateTime,default=datetime.utcnow,nullable=False)
    reviewed_at=Column(DateTime,nullable=True)
    __table_args__=(UniqueConstraint('case_id','campaign_id',name='uq_pruvs_demo_campaign_claim'),)

class RewardVoucher(Base):
    __tablename__='pruvs_reward_vouchers'
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,nullable=False,index=True)
    campaign_id=Column(Integer,ForeignKey('pruvs_reward_campaigns.id'),nullable=False)
    code=Column(String(60),nullable=False,unique=True)
    status=Column(String(20),nullable=False,default='issued')
    issued_at=Column(DateTime,default=datetime.utcnow,nullable=False)
    redeemed_at=Column(DateTime,nullable=True)
    __table_args__=(UniqueConstraint('user_id','campaign_id',name='uq_pruvs_demo_voucher_once'),)
