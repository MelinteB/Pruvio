"""Tenant-scoped location lifecycle, dependency summaries and management audit."""
from sqlalchemy import String, DateTime, Text, ForeignKey, inspect, select, func
from sqlalchemy.orm import Mapped, mapped_column
from fastapi import HTTPException
from .db import Base
from .models import Merchant, Store, Program, Membership, ReceiptClaim, Reward, Promotion, uid, utcnow
from datetime import datetime
import json

class ArchivedLocation(Base):
    __tablename__ = 'merchant_location_archives_v0624'
    store_id: Mapped[str] = mapped_column(ForeignKey('stores.id'), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ManagementAudit(Base):
    __tablename__ = 'merchant_management_audit_v0624'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    merchant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    object_type: Mapped[str] = mapped_column(String(20), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

def management_ready(db):
    i=inspect(db.connection())
    return i.has_table(ArchivedLocation.__tablename__) and i.has_table(ManagementAudit.__tablename__)

def require_management(db):
    if not management_ready(db):
        raise HTTPException(503,'Location management migration is not ready.')

def lock_merchant(db, merchant_id):
    db.scalar(select(Merchant).where(Merchant.id==merchant_id).with_for_update())

def archived(db, store):
    if not management_ready(db):return False
    row=db.get(ArchivedLocation,store.id)
    return bool(row and row.merchant_id==store.merchant_id)

def audit(db, staff, kind, object_id, action, details=None):
    if not management_ready(db):return
    db.add(ManagementAudit(merchant_id=staff.merchant_id,actor_id=staff.id,
                           object_type=kind,object_id=object_id,action=action,
                           details=json.dumps(details or {},ensure_ascii=False)))

def program_counts(db, p):
    count=lambda model, *where: db.scalar(select(func.count(model.id)).where(model.program_id==p.id,*where)) or 0
    outstanding=count(Reward,Reward.merchant_id==p.merchant_id,Reward.status.in_(('available','reserved')))
    return {'memberships':count(Membership),
            'pending_claims':count(ReceiptClaim,ReceiptClaim.merchant_id==p.merchant_id,ReceiptClaim.status=='pending'),
            'outstanding_rewards':outstanding,
            'outstanding_reward_minor':outstanding*p.reward_minor,
            'campaigns':count(Promotion,Promotion.merchant_id==p.merchant_id)}

def location_counts(db, store):
    programs=db.scalars(select(Program).where(Program.store_id==store.id,Program.merchant_id==store.merchant_id)).all()
    counts={'programs':len(programs),'published_programs':sum(p.status=='published' for p in programs),
            'pending_claims':0,'outstanding_rewards':0,'campaigns':0}
    for p in programs:
        summary=program_counts(db,p)
        for k in ('pending_claims','outstanding_rewards','campaigns'):counts[k]+=summary[k]
    return counts

def require_retirable(db,store):
    c=location_counts(db,store)
    if c['published_programs'] or c['pending_claims'] or c['outstanding_rewards']:
        raise HTTPException(409,'Pause published programs and resolve pending claims and outstanding rewards before deactivating this location.')

def prevent_duplicate_location(db,staff,payload,exclude=None):
    rows=db.scalars(select(Store).where(Store.merchant_id==staff.merchant_id)).all()
    normalized=lambda s:' '.join((s or '').casefold().split())
    for s in rows:
        if s.id!=exclude and normalized(s.name)==normalized(payload.name) and (
            normalized(s.address)==normalized(payload.address) or
            (abs(s.latitude-payload.latitude)<0.00001 and abs(s.longitude-payload.longitude)<0.00001)):
            raise HTTPException(409,'A matching location already exists. Edit or restore that location.')
