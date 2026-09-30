from datetime import datetime

from nicegui import ui

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
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, get_ui_language, login_user


def _login_view() -> None:
    lang = get_ui_language()
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-login-shell gap-6"):
            app_header("Smart receipt assistant", show_account=False, language=lang)

            with ui.row().classes("w-full items-stretch justify-between gap-6 flex-col lg:flex-row pt-4"):
                with ui.column().classes("flex-1 justify-center gap-4 lg:pr-8"):
                    ui.label(t("Receipts, simplified.", lang)).classes(
                        "text-4xl sm:text-5xl font-black text-slate-950 tracking-tight"
                    )
                    ui.label(t(
                        "Upload receipts, review OCR results, translate foreign item names and split bills with friends.",
                        lang,
                    )).classes("text-base sm:text-lg text-slate-500 max-w-2xl leading-relaxed")
                    with ui.row().classes("gap-2 flex-wrap"):
                        for text in ["Receipt OCR", "English translation", "Split bills", "OTP security"]:
                            ui.label(t(text, lang)).classes("metric-pill" + (" metric-accent" if text == "OTP security" else ""))

                with ui.card().classes("pruvio-card pruvio-login-card p-6 sm:p-7"):
                    ui.label(t("Sign in", lang)).classes("text-2xl font-black text-slate-950")
                    ui.label(
                        "Passkey, password, OTP, or developer Authenticator."
                        if lang == "en"
                        else "Passkey, parolă, OTP sau Authenticator pentru dezvoltator."
                    ).classes("text-sm text-slate-500")

                    status = ui.label("").classes("text-xs text-red-600")
                    debug = ui.label("").classes("text-xs text-amber-700")

                    async def sign_in_with_passkey():
                        status.set_text("")
                        debug.set_text("")
                        if not passkeys_enabled():
                            status.set_text("Passkeys are not enabled on this server yet." if lang == "en" else "Passkey-urile nu sunt activate încă pe server.")
                            return
                        try:
                            challenge, options_json = begin_passkey_authentication()
                            browser_result = await ui.run_javascript(
                                authentication_browser_javascript(options_json),
                                timeout=75.0,
                            )
                            db = SessionLocal()
                            try:
                                user = complete_passkey_authentication(
                                    db,
                                    challenge=challenge,
                                    browser_credential=browser_result,
                                )
                                target = login_user(user)
                            finally:
                                db.close()
                        except Exception as error:
                            status.set_text(str(error) or ("Passkey sign-in failed." if lang == "en" else "Autentificarea cu passkey a eșuat."))
                            return
                        ui.navigate.to(target)

                    ui.button(
                        t("Use fingerprint / Face ID / passkey", lang),
                        icon="fingerprint",
                        on_click=sign_in_with_passkey,
                    ).classes("pruvio-primary w-full py-3 mt-3")
                    ui.label(
                        "Your fingerprint or face stays on your device. Pruvio only verifies the signed passkey response."
                        if lang == "en"
                        else "Amprenta sau datele Face ID rămân pe dispozitiv. Pruvio verifică doar răspunsul criptografic al passkey-ului."
                    ).classes("text-[11px] text-slate-400 leading-relaxed")

                    with ui.row().classes("w-full items-center gap-3 my-1"):
                        ui.separator().classes("flex-1")
                        ui.label("or" if lang == "en" else "sau").classes("text-xs text-slate-400")
                        ui.separator().classes("flex-1")

                    identifier = ui.input(t("Email or phone number", lang)).props(
                        "outlined autocomplete=username"
                    ).classes("w-full")
                    password = ui.input(t("Password", lang), password=True, password_toggle_button=True).props(
                        "outlined autocomplete=current-password"
                    ).classes("w-full")

                    def password_login():
                        status.set_text("")
                        debug.set_text("")
                        db = SessionLocal()
                        try:
                            user = authenticate_with_password(db, identifier.value or "", password.value or "")
                            target = login_user(user)
                        except Exception as error:
                            status.set_text(str(error))
                            return
                        finally:
                            db.close()
                        ui.navigate.to(target)

                    ui.button(t("Sign in with password", lang), icon="lock_open", on_click=password_login).classes(
                        "pruvio-primary w-full py-3"
                    )
                    ui.label(t("Forgot password?", lang)).classes("pruvio-link text-xs self-end").on(
                        "click", lambda: ui.navigate.to("/reset-password")
                    )

                    otp_panel = ui.column().classes("w-full gap-3")
                    otp_panel.visible = False
                    with otp_panel:
                        otp = ui.input("Cod OTP" if lang == "ro" else "6-digit verification code").props(
                            "outlined inputmode=numeric maxlength=6 autocomplete=one-time-code"
                        ).classes("w-full")

                        def verify_login():
                            db = SessionLocal()
                            try:
                                user = complete_passwordless_login(
                                    db,
                                    identifier=identifier.value or "",
                                    code=otp.value or "",
                                )
                                target = login_user(user)
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            finally:
                                db.close()
                            ui.navigate.to(target)

                        ui.button(
                            "Verifică și autentifică" if lang == "ro" else "Verify and sign in",
                            icon="verified_user",
                            on_click=verify_login,
                        ).classes("pruvio-primary w-full py-3")

                    def send_code():
                        status.set_text("")
                        debug.set_text("")
                        db = SessionLocal()
                        try:
                            result = start_passwordless_login(db, identifier.value or "")
                        except Exception as error:
                            status.set_text(str(error))
                            return
                        finally:
                            db.close()

                        otp_panel.visible = True
                        destination = result["destination"]
                        channel = "email" if result["destination_type"] == "email" else "SMS"
                        status.classes("text-emerald-700", remove="text-red-600")
                        status.set_text(
                            f"Codul de verificare a fost trimis prin {channel} la {destination}."
                            if lang == "ro"
                            else f"Verification code sent by {channel} to {destination}."
                        )
                        if result.get("debug_otp"):
                            debug.set_text(
                                f"Cod debug OTP: {result['debug_otp']}"
                                if lang == "ro"
                                else f"Debug OTP: {result['debug_otp']}"
                            )

                    ui.button(t("Continue with OTP", lang), icon="sms", on_click=send_code).classes(
                        "pruvio-secondary w-full py-3"
                    )

                    if totp_debug_enabled():
                        dev_panel = ui.column().classes("w-full gap-2 mt-2")
                        dev_panel.visible = False
                        with dev_panel:
                            ui.label("Autentificare TOTP doar pentru dezvoltator" if lang == "ro" else "Developer-only TOTP debug login").classes("text-xs font-bold text-slate-500")
                            dev_code = ui.input(t("Authenticator code", lang)).props(
                                "outlined inputmode=numeric maxlength=6 autocomplete=one-time-code"
                            ).classes("w-full")

                        def open_dev_authenticator():
                            status.set_text("")
                            db = SessionLocal()
                            try:
                                user = get_account_for_identifier(db, identifier.value or "")
                                if not totp_allowed_for_user(user):
                                    raise ValueError("Developer Authenticator is not enabled for this account.")
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            finally:
                                db.close()
                            dev_panel.visible = True

                        def verify_dev_authenticator():
                            db = SessionLocal()
                            try:
                                user = get_account_for_identifier(db, identifier.value or "")
                                if not totp_allowed_for_user(user):
                                    raise ValueError("Developer Authenticator is not enabled for this account.")
                                if not verify_totp(dev_code.value or "", user=user):
                                    raise ValueError("Invalid Authenticator code.")
                                user.last_seen_at = datetime.utcnow()
                                db.commit()
                                db.refresh(user)
                                target = login_user(user)
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            finally:
                                db.close()
                            ui.navigate.to(target)

                        ui.button(t("Developer Authenticator", lang), icon="phonelink_lock", on_click=open_dev_authenticator).props(
                            "flat no-caps"
                        ).classes("w-full text-slate-500 text-xs")
                        with dev_panel:
                            ui.button(t("Verify Authenticator", lang), icon="verified", on_click=verify_dev_authenticator).classes(
                                "pruvio-secondary w-full"
                            )

                    ui.separator().classes("my-3")
                    with ui.row().classes("w-full justify-center gap-1 text-sm"):
                        ui.label(t("New to Pruvio?", lang)).classes("text-slate-500")
                        ui.label(t("Create account", lang)).classes("pruvio-link").on(
                            "click", lambda: ui.navigate.to("/register")
                        )
                    with ui.row().classes("w-full justify-center gap-3 mt-2"):
                        ui.label(t("Terms", lang)).classes("pruvio-link text-xs").on("click", lambda: ui.navigate.to("/terms"))
                        ui.label(t("Privacy", lang)).classes("pruvio-link text-xs").on("click", lambda: ui.navigate.to("/privacy"))
                        ui.label(t("Help", lang)).classes("pruvio-link text-xs").on("click", lambda: ui.navigate.to("/support"))


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
        setup_page_head("Pruvio")
        db = SessionLocal()
        try:
            user = get_logged_in_user(db)
        finally:
            db.close()
        if user is None:
            _login_view()
            return
        _dashboard(user)
