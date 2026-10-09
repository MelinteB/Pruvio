from nicegui import app as nicegui_app, ui
from sqlalchemy.orm import Session

from app.models.user import User
from app.i18n import normalize_language


USER_ID_KEY = "user_id"
POST_LOGIN_PATH_KEY = "post_login_path"
UI_LANGUAGE_KEY = "ui_language"


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


def get_ui_language(default: str = "en") -> str:
    return normalize_language(nicegui_app.storage.user.get(UI_LANGUAGE_KEY, default))


def set_ui_language(language: str) -> None:
    nicegui_app.storage.user[UI_LANGUAGE_KEY] = normalize_language(language)


def login_user(user: User) -> str:
    from app.services.push_service import revoke_grant
    revoke_grant(nicegui_app.storage.user.pop("push_grant", None))
    nicegui_app.storage.user[USER_ID_KEY] = user.id
    set_ui_language(user.preferred_language or "en")
    target = nicegui_app.storage.user.pop(POST_LOGIN_PATH_KEY, None)
    nicegui_app.storage.user["push_next"] = str(target or "/")
    return "/notifications"


def logout_user() -> None:
    from app.services.push_service import revoke_grant
    revoke_grant(nicegui_app.storage.user.get("push_grant"))
    ui.run_javascript("navigator.serviceWorker?.getRegistration('/').then(async r => { if (r) { for (const n of await r.getNotifications()) n.close(); } }).catch(() => {});")
    language = get_ui_language()
    nicegui_app.storage.user.clear()
    nicegui_app.storage.user[UI_LANGUAGE_KEY] = language


def require_login(return_to: str) -> int | None:
    user_id = get_logged_in_user_id()
    if user_id is not None:
        return user_id

    nicegui_app.storage.user[POST_LOGIN_PATH_KEY] = return_to
    ui.navigate.to("/")
    return None
