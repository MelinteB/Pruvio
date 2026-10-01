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

