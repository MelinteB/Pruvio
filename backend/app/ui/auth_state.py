from nicegui import app as nicegui_app, ui
from sqlalchemy.orm import Session

from app.models.user import User


USER_ID_KEY = "user_id"
POST_LOGIN_PATH_KEY = "post_login_path"


def get_logged_in_user_id() -> int | None:
    raw = nicegui_app.storage.user.get(USER_ID_KEY)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def get_logged_in_user(db: Session) -> User | None:
    user_id = get_logged_in_user_id()
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def login_user(user: User) -> str:
    nicegui_app.storage.user[USER_ID_KEY] = user.id
    target = nicegui_app.storage.user.pop(POST_LOGIN_PATH_KEY, None)
    return str(target or "/")


def logout_user() -> None:
    nicegui_app.storage.user.clear()


def require_login(return_to: str) -> int | None:
    user_id = get_logged_in_user_id()
    if user_id is not None:
        return user_id

    nicegui_app.storage.user[POST_LOGIN_PATH_KEY] = return_to
    ui.navigate.to("/")
    return None
