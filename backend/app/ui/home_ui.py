from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.auth_service import authenticate_with_password
from app.services.passkey_service import (
    authentication_browser_javascript,
    begin_passkey_authentication,
    complete_passkey_authentication,
    passkeys_enabled,
)
from app.services.standalone_app_service import list_recent_receipts
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, get_ui_language, login_user


def _login_view() -> None:
    lang = get_ui_language()
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-login-shell gap-6"):
            app_header("Smart receipt assistant", show_account=False, language=lang)
            with ui.row().classes("w-full items-stretch justify-between gap-6 flex-col lg:flex-row pt-4"):
                with ui.column().classes("flex-1 justify-center gap-4 lg:pr-8"):
                    ui.label(t("Receipts, simplified.", lang)).classes("text-4xl sm:text-5xl font-black text-slate-950 tracking-tight")
                    ui.label(t("Upload receipts, review OCR results, translate foreign item names and split bills with friends.", lang)).classes("text-base sm:text-lg text-slate-500 max-w-2xl leading-relaxed")
                    with ui.row().classes("gap-2 flex-wrap"):
                        for text in ["Receipt OCR", "English translation", "Split bills"]:
                            ui.label(t(text, lang)).classes("metric-pill")
                with ui.card().classes("pruvio-card pruvio-login-card p-6 sm:p-7"):
                    ui.label(t("Sign in", lang)).classes("text-2xl font-black text-slate-950")
                    ui.label("Autentifică-te cu un passkey sau cu numele de utilizator / emailul și parola." if lang == "ro" else "Sign in with a passkey or your username / email and password.").classes("text-sm text-slate-500")
                    status = ui.label("").classes("text-xs text-red-600")

                    async def sign_in_with_passkey():
                        status.set_text("")
                        if not passkeys_enabled():
                            status.set_text("Passkeys are not enabled on this server yet.")
                            return
                        try:
                            challenge, options = begin_passkey_authentication()
                            credential = await ui.run_javascript(authentication_browser_javascript(options), timeout=75)
                            db = SessionLocal()
                            try:
                                user = complete_passkey_authentication(db, challenge=challenge, browser_credential=credential)
                                ui.navigate.to(login_user(user))
                            finally:
                                db.close()
                        except Exception as error:
                            status.set_text(str(error) or "Passkey sign-in failed.")

                    passkey_button = ui.button(t("Use fingerprint / Face ID / passkey", lang), icon="fingerprint", on_click=sign_in_with_passkey).classes("pruvio-primary w-full py-3 mt-3")
                    passkey_button.visible = passkeys_enabled()
                    ui.label("Amprenta și datele Face ID rămân pe dispozitiv." if lang == "ro" else "Your fingerprint and Face ID data stay on your device.").classes("text-[11px] text-slate-400")
                    identifier = ui.input("Nume utilizator sau email" if lang == "ro" else "Username or email").props("outlined autocomplete=username debounce=350").classes("w-full")
                    password = ui.input(t("Password", lang), password=True, password_toggle_button=True).props("outlined autocomplete=current-password").classes("w-full")

                    async def password_login():
                        status.set_text("")
                        db = SessionLocal()
                        try:
                            user = authenticate_with_password(db, identifier.value or "", password.value or "")
                            ui.navigate.to(login_user(user))
                        except Exception as error:
                            status.set_text(str(error))
                        finally:
                            db.close()

                    ui.button(t("Sign in with password", lang), icon="lock_open", on_click=password_login).classes("pruvio-primary w-full py-3")
                    ui.label(t("Forgot password?", lang)).classes("pruvio-link text-xs self-end").on("click", lambda: ui.navigate.to("/reset-password"))
                    ui.separator().classes("my-3")
                    with ui.row().classes("w-full justify-center gap-1 text-sm"):
                        ui.label(t("New to Pruvs?", lang)).classes("text-slate-500")
                        ui.label(t("Create account", lang)).classes("pruvio-link").on("click", lambda: ui.navigate.to("/register"))
                    with ui.row().classes("w-full justify-center gap-3 mt-2"):
                        for text, path in [("Terms", "/terms"), ("Privacy", "/privacy"), ("Help", "/support")]:
                            ui.label(t(text, lang)).classes("pruvio-link text-xs").on("click", lambda p=path: ui.navigate.to(p))


def _dashboard(user) -> None:
    lang = user.preferred_language or get_ui_language()
    db = SessionLocal()
    try:
        recent = list_recent_receipts(db, user_id=user.id, limit=6)
    finally:
        db.close()

    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Smart receipt assistant", language=lang)

            with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                with ui.column().classes("gap-3"):
                    greeting = f"Salut, {user.name or 'acolo'}." if lang == "ro" else f"Hi, {user.name or 'there'}."
                    ui.label(greeting).classes("text-3xl sm:text-4xl font-black text-slate-950 tracking-tight")
                    ui.label(
                        "Scanează un bon, verifică produsele extrase, împarte nota sau deschide un bon din istoric."
                        if lang == "ro"
                        else "Scan a receipt, review the extracted items, split a bill, or open something from your history."
                    ).classes("text-sm sm:text-base text-slate-500 max-w-2xl")
                    with ui.row().classes("gap-3 mt-2 flex-wrap"):
                        ui.button(
                            "Scanează sau încarcă bon" if lang == "ro" else "Scan or upload receipt",
                            icon="photo_camera",
                            on_click=lambda: ui.navigate.to("/upload"),
                        ).classes("pruvio-primary px-5 py-3")
                        ui.button(t("Receipt history", lang), icon="history", on_click=lambda: ui.navigate.to("/history")).classes(
                            "pruvio-secondary px-5 py-3"
                        )

            with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label("Bonuri recente" if lang == "ro" else "Recent receipts").classes("text-lg font-black text-slate-950")
                        ui.label("Cele mai recente bonuri procesate" if lang == "ro" else "Your latest processed receipts").classes("text-xs text-slate-500")
                    if recent:
                        ui.label("Vezi toate" if lang == "ro" else "View all").classes("pruvio-link text-xs").on(
                            "click", lambda: ui.navigate.to("/history")
                        )

                if not recent:
                    with ui.column().classes("w-full items-center py-8 gap-2"):
                        ui.icon("receipt_long", size="42px").classes("text-slate-300")
                        ui.label(t("No receipts yet.", lang)).classes("font-bold text-slate-600")
                        ui.label(t("Upload your first receipt to start.", lang)).classes("text-sm text-slate-400")
                else:
                    with ui.column().classes("w-full gap-0 mt-2"):
                        for receipt in recent:
                            created = receipt["created_at"].strftime("%d %b %Y · %H:%M")
                            with ui.row().classes("item-row w-full items-center justify-between gap-3 py-3 cursor-pointer").on(
                                "click", lambda _, case_id=receipt["case_id"]: ui.navigate.to(f"/receipt/{case_id}"),
                            ):
                                with ui.column().classes("gap-0 min-w-0"):
                                    ui.label(receipt["merchant_name"]).classes("font-bold text-slate-900 truncate")
                                    ui.label(created).classes("text-xs text-slate-400")
                                ui.label(f"{receipt['total']:.2f} {receipt['currency']}").classes("font-black text-slate-950 whitespace-nowrap")
        bottom_nav("home", lang)


def setup_home_ui() -> None:
    @ui.page("/")
    def home_page():
        setup_page_head("Pruvs")
        db = SessionLocal()
        try:
            user = get_logged_in_user(db)
        finally:
            db.close()
        if user is None:
            _login_view()
            return
        _dashboard(user)
