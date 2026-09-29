from datetime import datetime

from nicegui import ui

from app.db.database import SessionLocal
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, logout_user, require_login


def setup_account_ui() -> None:
    @ui.page("/account")
    def account_page():
        setup_page_head("Account · Pruvio")
        user_id = require_login("/account")
        if user_id is None:
            return

        db = SessionLocal()
        try:
            user = get_logged_in_user(db)
        finally:
            db.close()
        if user is None:
            logout_user()
            ui.navigate.to("/")
            return

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Account")

                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label(user.name or "Pruvio user").classes("text-3xl font-black text-slate-950")
                    ui.label(user.email or "No email").classes("text-sm text-slate-500")
                    ui.label(user.phone_number).classes("text-sm text-slate-500")
                    with ui.row().classes("gap-2 flex-wrap mt-3"):
                        ui.label("Email verified" if user.is_email_verified else "Email not verified").classes(
                            "metric-pill metric-accent" if user.is_email_verified else "metric-pill"
                        )
                        ui.label("Phone verified" if user.is_phone_verified else "Phone not verified").classes(
                            "metric-pill metric-accent" if user.is_phone_verified else "metric-pill"
                        )
                        ui.label("Active account" if user.status == "active" else user.status).classes("metric-pill")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label("Profile & preferences").classes("text-lg font-black text-slate-950")
                    name = ui.input("Display name", value=user.name or "").props("outlined").classes("w-full mt-3")
                    language = ui.select(
                        {"en": "English", "ro": "Romanian"},
                        value=user.preferred_language or "en",
                        label="App language",
                    ).props("outlined").classes("w-full")
                    notifications = ui.checkbox("Product notifications", value=bool(user.notifications_opt_in))
                    marketing = ui.checkbox("Product news and marketing", value=bool(user.marketing_opt_in))
                    save_status = ui.label("").classes("text-xs text-emerald-700")

                    def save_preferences():
                        db_save = SessionLocal()
                        try:
                            from app.models.user import User
                            row = db_save.query(User).filter(User.id == user_id).first()
                            if not row:
                                raise ValueError("Account not found.")
                            row.name = (name.value or "").strip() or row.name
                            row.preferred_language = language.value or "en"
                            row.notifications_opt_in = bool(notifications.value)
                            row.marketing_opt_in = bool(marketing.value)
                            row.updated_at = datetime.utcnow()
                            db_save.commit()
                        except Exception as error:
                            save_status.classes("text-red-600", remove="text-emerald-700")
                            save_status.set_text(str(error))
                            return
                        finally:
                            db_save.close()
                        save_status.classes("text-emerald-700", remove="text-red-600")
                        save_status.set_text("Preferences saved.")

                    ui.button("Save preferences", on_click=save_preferences).classes("pruvio-primary mt-3")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label("Security & legal").classes("text-lg font-black text-slate-950")
                    with ui.column().classes("w-full gap-2 mt-3"):
                        ui.button("Terms of Use", icon="description", on_click=lambda: ui.navigate.to("/terms")).classes("pruvio-secondary w-full")
                        ui.button("Privacy Notice", icon="privacy_tip", on_click=lambda: ui.navigate.to("/privacy")).classes("pruvio-secondary w-full")
                        ui.button("Help & support", icon="help", on_click=lambda: ui.navigate.to("/support")).classes("pruvio-secondary w-full")
                    ui.label(
                        "Changing verified email/phone and self-service account deletion are planned next; until then contact support."
                    ).classes("text-xs text-slate-400 mt-3")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label("Session").classes("text-lg font-black text-slate-950")
                    def sign_out():
                        logout_user()
                        ui.navigate.to("/")
                    ui.button("Sign out", icon="logout", on_click=sign_out).classes("pruvio-secondary mt-3")
        bottom_nav("account")
