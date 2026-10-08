import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserAdminResponse,
    UserAdminUpdate,
    UserAdminCreate,
    UserStatus,
)
from app.services.account_service import delete_user_completely, request_account_deletion_otp
from app.services.onboarding_otp_service import normalize_email, normalize_phone_number
from app.services.user_service import create_user, get_user_by_id, update_user_admin

router = APIRouter()

_admin_key_header = APIKeyHeader(
    name="X-Pruvs-Admin-Key",
    auto_error=False,
    description="Pruvs administrator API key.",
)


def _expected_admin_api_key() -> str:
    # New PRUVS_* name is preferred. Keep the old PRUVIO_* variable for
    # backwards compatibility with existing Render environments.
    return (
        os.getenv("PRUVS_ADMIN_API_KEY", "").strip()
        or os.getenv("PRUVIO_ADMIN_API_KEY", "").strip()
    )


def _validate_admin_api_key(provided: str | None) -> None:
    expected = _expected_admin_api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API is not configured.")
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid admin API key.")


def require_admin_api_key(
    x_pruvs_admin_key: str | None = Security(_admin_key_header),
    request: Request = None,
) -> None:
    """
    Require the Pruvs admin API key.

    X-Pruvs-Admin-Key is the documented header. X-Pruvio-Admin-Key remains
    accepted as a hidden compatibility fallback for older integrations.
    """
    provided = x_pruvs_admin_key
    if not provided and request is not None:
        provided = request.headers.get("X-Pruvio-Admin-Key")
    _validate_admin_api_key(provided)


@router.get(
    "/",
    response_model=list[UserAdminResponse],
    dependencies=[Depends(require_admin_api_key)],
    summary="List users",
)
def list_users(
    status: UserStatus | None = Query(default=None),
    email_verified: bool | None = Query(default=None),
    is_admin: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100, description="Search username, name, email or phone."),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Admin-only user list with optional filtering and pagination."""
    query = db.query(User)

    if is_admin is not None:
        query = query.filter(User.is_admin.is_(is_admin))
    if status is not None:
        query = query.filter(User.status == status)
    if email_verified is not None:
        query = query.filter(User.is_email_verified.is_(email_verified))
    if q and q.strip():
        search = f"%{q.strip()}%"
        query = query.filter(
            or_(
                User.username.ilike(search),
                User.name.ilike(search),
                User.email.ilike(search),
                User.phone_number.ilike(search),
            )
        )

    return (
        query.order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get(
    "/stats",
    dependencies=[Depends(require_admin_api_key)],
    summary="User statistics",
)
def user_stats(db: Session = Depends(get_db)):
    """Small operational summary for the admin user collection."""
    total = db.query(func.count(User.id)).scalar() or 0
    active = db.query(func.count(User.id)).filter(User.status == "active").scalar() or 0
    pending = db.query(func.count(User.id)).filter(User.status == "pending_join").scalar() or 0
    blocked = db.query(func.count(User.id)).filter(User.status == "blocked").scalar() or 0
    verified_email = (
        db.query(func.count(User.id))
        .filter(User.is_email_verified.is_(True))
        .scalar()
        or 0
    )
    return {
        "total": total,
        "administrators": db.query(func.count(User.id)).filter(User.is_admin.is_(True)).scalar() or 0,
        "active": active,
        "pending_join": pending,
        "blocked": blocked,
        "email_verified": verified_email,
        "email_unverified": max(0, total - verified_email),
    }


@router.get(
    "/{user_id}",
    response_model=UserAdminResponse,
    dependencies=[Depends(require_admin_api_key)],
    summary="Get user",
)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.post(
    "/",
    response_model=UserAdminResponse,
    status_code=201,
    dependencies=[Depends(require_admin_api_key)],
    summary="Create user",
)
def add_user(user_data: UserAdminCreate, db: Session = Depends(get_db)):
    try:
        normalized_phone = normalize_phone_number(user_data.phone_number)
        normalized_email = normalize_email(str(user_data.email)) if user_data.email else None

        existing_phone = db.query(User.id).filter(User.phone_number == normalized_phone).first()
        if existing_phone:
            raise HTTPException(status_code=409, detail="Phone number is already in use.")

        if normalized_email:
            existing_email = (
                db.query(User.id)
                .filter(func.lower(User.email) == normalized_email)
                .first()
            )
            if existing_email:
                raise HTTPException(status_code=409, detail="Email address is already in use.")

        normalized_data = user_data.model_copy(
            update={"phone_number": normalized_phone, "email": normalized_email}
        )
        from app.services.admin_dashboard_service import add_audit
        add_audit(db, None, "api_key", "create", "users", None, ["is_admin"] if user_data.is_admin else [])
        user = create_user(db, normalized_data)
        if normalized_email:
            user.email = normalized_email
            db.commit()
            db.refresh(user)
        return user
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.patch(
    "/{user_id}",
    response_model=UserAdminResponse,
    dependencies=[Depends(require_admin_api_key)],
    summary="Edit user",
    responses={
        404: {"description": "User not found"},
        409: {"description": "Username, email, phone number, or another unique value conflicts with another user"},
    },
)
def edit_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: Session = Depends(get_db),
):
    """
    Edit an existing user using only the admin key.

    No OTP, active-account requirement, or verified-email requirement is used.
    If email or phone changes, its verification flag is reset automatically
    unless the administrator explicitly supplies the corresponding verification
    field in the same PATCH request.
    """
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        from app.services.admin_dashboard_service import add_audit
        add_audit(db, None, "api_key", "update", "users", user_id, sorted(payload.model_fields_set))
        return update_user_admin(db, user, payload)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.delete(
    "/{user_id}",
    dependencies=[Depends(require_admin_api_key)],
    summary="Delete user permanently",
)
def delete_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """
    Permanently delete a user and the user's Pruvs data using the admin API key.

    This administrative operation intentionally does not require an OTP, an
    active account, or a verified email address. End-user account deletion from
    the Account UI continues to require email OTP confirmation.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        from app.services.admin_dashboard_service import add_audit
        add_audit(db, None, "api_key", "delete", "users", user_id)
        delete_user_completely(db, user)
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"User deletion failed: {error}")

    return {
        "deleted": True,
        "user_id": user_id,
        "verification_required": False,
    }


@router.post(
    "/{user_id}/deletion-otp",
    dependencies=[Depends(require_admin_api_key)],
    include_in_schema=False,
)
def request_deletion_otp(user_id: int, db: Session = Depends(get_db)):
    """Legacy endpoint retained for compatibility; admin deletion no longer uses OTP."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="User not found.")
    try:
        return request_account_deletion_otp(db, user, "email")
    except ValueError as error:
        raise HTTPException(400, detail=str(error))
