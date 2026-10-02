import re
import unicodedata

from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.usernames import normalize_username, username_key


def check_username_available(db, value: str, *, exclude_user_id: int | None = None) -> str:
    clean = normalize_username(value)
    query = db.query(User.id).filter(User.username_key == username_key(clean))
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    if query.first():
        raise ValueError("This username is already taken. Choose another username.")
    return clean


def _username_name_part(value: str) -> str:
    """Turn a name component into a stable URL/login-friendly component."""
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    clean = re.sub(r"[^A-Za-z0-9-]+", "", folded).strip("-").lower()
    return clean


def username_base_from_name(full_name: str) -> str:
    """Derive the default username from first name + surname (e.g. ana.popescu)."""
    name = " ".join((full_name or "").split())
    if not name:
        raise ValueError("Full name is required.")

    parts = name.split()
    first = _username_name_part(parts[0])
    last = _username_name_part(parts[-1]) if len(parts) > 1 else ""
    if first and last:
        base = f"{first}.{last}"
    else:
        base = first or last

    if len(base) < 3:
        # Very short names still need to satisfy the username validation rules.
        base = f"user.{base or 'member'}"

    return normalize_username(base[:80].rstrip("."))


def derive_available_username(
    db,
    full_name: str,
    *,
    exclude_user_id: int | None = None,
) -> str:
    """Derive first.surname and add .2, .3, ... only when a collision exists."""
    base = username_base_from_name(full_name)
    candidate = base
    suffix = 2

    while True:
        query = db.query(User.id).filter(User.username_key == username_key(candidate))
        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)
        if not query.first():
            return candidate

        ending = f".{suffix}"
        trimmed = base[: 80 - len(ending)].rstrip(".")
        candidate = normalize_username(f"{trimmed}{ending}")
        suffix += 1


def update_username(db, user, value: str):
    user.username = check_username_available(db, value, exclude_user_id=user.id)
    user.username_key = username_key(user.username)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("This username is already taken. Choose another username.")
    db.refresh(user)
    return user
