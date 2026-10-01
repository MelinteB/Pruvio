from datetime import datetime

from nicegui import ui
from fastapi import Request

from app.db.database import SessionLocal
from app.i18n import t
from app.services.auth_service import (
    authenticate_with_password,
    complete_passwordless_login,
    get_account_for_identifier,
    start_passwordless_login,
)
from app.services.passkey_service import (
    authentication_browser_javascript,
    begin_passkey_authentication,
    complete_passkey_authentication,
    passkeys_enabled,
)
from app.services.standalone_app_service import list_recent_receipts
from app.services.totp_debug_service import (
    totp_allowed_for_user,
    totp_debug_enabled,
    verify_totp,
)
from app.services.trusted_device_service import DEVICE_COOKIE, is_trusted_device, trusted_device_days
from app.ui.device_login import finish_verified_device_login
from app.ui.email_otp_dialog import EmailOTPDialog
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, get_ui_language, login_user


def _login_view(device_token: str | None = None) -> None:
    lang = get_ui_language()
    state = {"challenge_id": None, "challenge_identifier": None, "verified_user_id": None}
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-login-shell gap-6"):
            app_header("Smart receipt assistant", show_account=False, language=lang)
            with ui.row().classes("w-full items-stretch justify-between gap-6 flex-col lg:flex-row pt-4"):
                with ui.column().classes("flex-1 justify-center gap-4 lg:pr-8"):
                    ui.label(t("Receipts, simplified.", lang)).classes("text-4xl sm:text-5xl font-black text-slate-950 tracking-tight")
                    ui.label(t("Upload receipts, review OCR results, translate foreign item names and split bills with friends.", lang)).classes("text-base sm:text-lg text-slate-500 max-w-2xl leading-relaxed")
                    with ui.row().classes("gap-2 flex-wrap"):
                        for text in ["Receipt OCR", "English translation", "Split bills", "OTP security"]:
                            ui.label(t(text, lang)).classes("metric-pill")
                with ui.card().classes("pruvio-card pruvio-login-card p-6 sm:p-7"):
                    ui.label(t("Sign in", lang)).classes("text-2xl font-black text-slate-950")
                    ui.label("Parolă sau passkey. Solicităm OTP doar într-un browser nou sau expirat." if lang == "ro" else "Password or passkey. OTP is requested only in a new or expired browser.").classes("text-sm text-slate-500")
                    status = ui.label("").classes("text-xs text-red-600")

                    async def finish_credential_login(db, user):
                        if is_trusted_device(db, user, device_token):
                            ui.navigate.to(login_user(user))
                            return
                        identifier.set_value(user.username or user.email)
                        refresh_device_options()
                        send_code()

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
                                await finish_credential_login(db, user)
                            finally:
                                db.close()
                        except Exception as error:
                            status.set_text(str(error) or "Passkey sign-in failed.")

                    ui.button(t("Use fingerprint / Face ID / passkey", lang), icon="fingerprint", on_click=sign_in_with_passkey).classes("pruvio-primary w-full py-3 mt-3")
                    ui.label("Amprenta și datele Face ID rămân pe dispozitiv." if lang == "ro" else "Your fingerprint and Face ID data stay on your device.").classes("text-[11px] text-slate-400")
                    identifier = ui.input("Nume utilizator sau email" if lang == "ro" else "Username or email").props("outlined autocomplete=username debounce=350").classes("w-full")
                    password = ui.input(t("Password", lang), password=True, password_toggle_button=True).props("outlined autocomplete=current-password").classes("w-full")

                    async def password_login():
                        status.set_text("")
                        db = SessionLocal()
                        try:
                            user = authenticate_with_password(db, identifier.value or "", password.value or "")
                            await finish_credential_login(db, user)
                        except Exception as error:
                            status.set_text(str(error))
                        finally:
                            db.close()

                    ui.button(t("Sign in with password", lang), icon="lock_open", on_click=password_login).classes("pruvio-primary w-full py-3")
                    ui.label(t("Forgot password?", lang)).classes("pruvio-link text-xs self-end").on("click", lambda: ui.navigate.to("/reset-password"))
                    device_note = ui.label("").classes("text-xs text-slate-500")
                    async def verify_login(code):
                        db = SessionLocal()
                        try:
                            if not state["challenge_id"]:
                                raise ValueError("Request a code from this sign-in screen first.")
                            if state["verified_user_id"]:
                                from app.models.user import User
                                user = db.get(User, state["verified_user_id"])
                                if not user or user.status != "active" or not user.is_email_verified:
                                    raise ValueError("Your account has changed. Start sign-in again.")
                            else:
                                user = complete_passwordless_login(db, state["challenge_identifier"], code,
                                    challenge_id=state["challenge_id"], device_token=device_token)
                                state["verified_user_id"] = user.id
                            target = await finish_verified_device_login(db, user)
                            state["challenge_id"] = None
                        finally:
                            db.close()
                        ui.navigate.to(target)

                    def request_login_code():
                        db = SessionLocal()
                        try:
                            result = start_passwordless_login(db, identifier.value or "", device_token=device_token)
                            state["verified_user_id"] = None
                            state["challenge_id"] = result["challenge_id"]
                            state["challenge_identifier"] = identifier.value
                            return result
                        finally:
                            db.close()

                    otp_dialog = EmailOTPDialog(
                        title="Verifică acest browser" if lang == "ro" else "Verify this browser",
                        description=(f"Confirmă emailul pentru a memora acest browser timp de {trusted_device_days()} zile." if lang == "ro"
                            else f"Confirm your email to remember this browser for {trusted_device_days()} days."),
                        on_verify=verify_login, on_resend=request_login_code, language=lang,
                        confirm_label="Verifică și autentifică" if lang == "ro" else "Verify and sign in")

                    def send_code():
                        status.set_text("")
                        try:
                            otp_dialog.present(request_login_code())
                        except Exception as error:
                            status.set_text(str(error))

                    otp_button = ui.button("Autentificare cu un cod pe email" if lang == "ro" else "Sign in with email code",
                        icon="mail_outline", on_click=send_code).classes("pruvio-secondary w-full py-3")
                    otp_button.visible = False

                    def refresh_device_options():
                        state["challenge_id"] = None
                        state["challenge_identifier"] = None
                        state["verified_user_id"] = None
                        otp_dialog.close()
                        db = SessionLocal()
                        try:
                            user = get_account_for_identifier(db, identifier.value or "") if identifier.value else None
                            trusted = is_trusted_device(db, user, device_token)
                            otp_button.visible = bool(user and user.status == "active" and not trusted)
                            device_note.set_text(("Browser verificat. Folosește parola sau passkey." if lang == "ro" else "Verified browser. Use your password or passkey.") if trusted else "")
                        except ValueError:
                            otp_button.visible = False
                            device_note.set_text("")
                        finally:
                            db.close()

                    identifier.on_value_change(lambda _: refresh_device_options())
                    if totp_debug_enabled():
                        dev_code = ui.input(t("Authenticator code", lang)).props("outlined inputmode=numeric maxlength=6").classes("w-full")
                        async def verify_dev_authenticator():
                            db = SessionLocal()
                            try:
                                user = get_account_for_identifier(db, identifier.value or "")
                                if not totp_allowed_for_user(user) or not verify_totp(dev_code.value or "", user=user):
                                    raise ValueError("Invalid developer Authenticator code.")
                                await finish_credential_login(db, user)
                            except Exception as error:
                                status.set_text(str(error))
                            finally:
                                db.close()
                        ui.button(t("Verify Authenticator", lang), on_click=verify_dev_authenticator).props("flat").classes("w-full text-slate-500 text-xs")
                    ui.separator().classes("my-3")
                    with ui.row().classes("w-full justify-center gap-1 text-sm"):
                        ui.label(t("New to Pruvio?", lang)).classes("text-slate-500")
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
    def home_page(request: Request):
        setup_page_head("Pruvio")
        db = SessionLocal()
        try:
            user = get_logged_in_user(db)
        finally:
            db.close()
        if user is None:
            _login_view(request.cookies.get(DEVICE_COOKIE))
            return
        _dashboard(user)
