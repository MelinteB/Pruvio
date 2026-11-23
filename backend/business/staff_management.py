"""Tenant-scoped merchant team management. No platform_admin self-provisioning.

Owners may invite, change roles and disable staff. All writes are audited. An
invite is inactive until the recipient uses their email-delivered setup link.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, inspect, select
from sqlalchemy.orm import Session

from .db import Base, get_db
from .models import Staff, Merchant
from .security import merchant_actor, hasher
from .merchant_enrollment import enforce_limit
from .password_recovery import _enabled as require_recovery, _send_reset

router = APIRouter(prefix="/v1/merchant/staff", tags=["Merchant team"])


class MerchantStaffAudit(Base):
    __tablename__ = "merchant_staff_actions_v1"
    id = Column(String(36), primary_key=True)
    merchant_id = Column(String(36), nullable=False, index=True)
    actor_id = Column(String(36), nullable=False)
    target_id = Column(String(36), nullable=False)
    action = Column(String(32), nullable=False)
    before_role = Column(String(20))
    after_role = Column(String(20))
    before_active = Column(Boolean)
    after_active = Column(Boolean)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class StaffInvitation(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(manager|staff)$")


class StaffUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(owner|manager|staff)$")
    active: bool | None = None
    confirm: str = Field(min_length=36, max_length=36)


def _staff_json(row: Staff):
    return {"id": row.id, "email": row.email, "role": row.role, "active": row.active}


def _owner(actor: Staff):
    if actor.role != "owner" or not actor.active:
        raise HTTPException(403, "Merchant owner permission required")


def _audit_ready(db: Session):
    if not inspect(db.get_bind()).has_table(MerchantStaffAudit.__tablename__):
        raise HTTPException(503, "Merchant staff management migration has not been applied")


def _log(db: Session, actor: Staff, target: Staff, action: str, before_role=None, before_active=None):
    db.add(MerchantStaffAudit(
        id=secrets.token_hex(16), merchant_id=actor.merchant_id, actor_id=actor.id,
        target_id=target.id, action=action, before_role=before_role,
        after_role=target.role, before_active=before_active, after_active=target.active,
    ))


@router.get("")
def list_staff(actor: Staff = Depends(merchant_actor), db: Session = Depends(get_db)):
    rows = db.scalars(select(Staff).where(Staff.merchant_id == actor.merchant_id).order_by(Staff.email)).all()
    return {"staff": [_staff_json(row) for row in rows] if actor.role == "owner"
            else [_staff_json(row) for row in rows if row.id == actor.id],
            "can_manage": actor.role == "owner", "me": actor.id}


@router.post("/invite", status_code=201)
def invite_staff(data: StaffInvitation, actor: Staff = Depends(merchant_actor),
                 db: Session = Depends(get_db)):
    _owner(actor)
    require_recovery(db)
    _audit_ready(db)
    email = str(data.email).strip().lower()
    # Business owner is authenticated before limits; only the owning tenant
    # may create a staff membership; email is globally unique by schema.
    enforce_limit(db, "staff-invite-owner:" + actor.id, max_attempts=12)
    enforce_limit(db, "staff-invite-email:" + email, max_attempts=3)
    if db.scalar(select(Staff.id).where(Staff.email == email)):
        raise HTTPException(409, "This email already belongs to a merchant account")
    merchant = db.get(Merchant, actor.merchant_id)
    if not merchant or merchant.status != "active":
        raise HTTPException(409, "Merchant must be active to invite team members")
    staff = Staff(merchant_id=actor.merchant_id, email=email,
                  password_hash=hasher.hash(secrets.token_urlsafe(48)),
                  role=data.role, active=False)
    db.add(staff);db.flush()
    _log(db, actor, staff, "invite", None, None)
    # If delivery fails the invite and audit are not committed.
    _send_reset(staff, invite=True)
    db.commit()
    return {"staff": _staff_json(staff), "message": "Invitation sent. Member must set a password."}


@router.patch("/{staff_id}")
def update_staff(staff_id: str, data: StaffUpdate,
                 actor: Staff = Depends(merchant_actor), db: Session = Depends(get_db)):
    _owner(actor)
    _audit_ready(db)
    if data.confirm != staff_id:
        raise HTTPException(422, "Confirm the team member ID to continue")
    target = db.scalar(select(Staff).where(
        Staff.id == staff_id, Staff.merchant_id == actor.merchant_id).with_for_update())
    if not target:
        raise HTTPException(404, "Merchant team member not found")
    new_role = data.role if data.role is not None else target.role
    new_active = data.active if data.active is not None else target.active
    if target.id == actor.id and (not new_active or new_role != "owner"):
        raise HTTPException(409, "You cannot disable or remove your own owner access")
    if target.role == "owner" and (new_role != "owner" or not new_active):
        owners = db.scalars(select(Staff).where(
            Staff.merchant_id == actor.merchant_id,
            Staff.role == "owner", Staff.active.is_(True)
        ).with_for_update()).all()
        if len(owners) <= 1:
            raise HTTPException(409, "Cannot remove the last active merchant owner")
    old_role, old_active = target.role, target.active
    target.role, target.active = new_role, new_active
    if old_active and not new_active:
        # An outstanding invite/reset token can never reactivate a revoked user.
        target.password_hash = hasher.hash(secrets.token_urlsafe(48))
    _log(db, actor, target, "update", old_role, old_active)
    db.commit()
    return {"staff": _staff_json(target)}


@router.get("/audit")
def staff_audit(actor: Staff = Depends(merchant_actor), db: Session = Depends(get_db)):
    _owner(actor)
    _audit_ready(db)
    rows = db.scalars(select(MerchantStaffAudit).where(
        MerchantStaffAudit.merchant_id == actor.merchant_id
    ).order_by(MerchantStaffAudit.created_at.desc()).limit(100)).all()
    return [{"actor_id": r.actor_id, "target_id": r.target_id,
             "action": r.action, "before_role": r.before_role,
             "after_role": r.after_role, "before_active": r.before_active,
             "after_active": r.after_active, "created_at": r.created_at.isoformat()}
            for r in rows]
