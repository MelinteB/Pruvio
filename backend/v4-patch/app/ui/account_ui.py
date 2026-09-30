from datetime import datetime

from nicegui import ui

from app.db.database import SessionLocal
from app.services.passkey_service import (
    begin_passkey_registration,
    complete_passkey_registration,
    delete_passkey,
    list_user_passkeys,
    passkey_config_summary,
    passkeys_enabled,
    registration_browser_javascript,
)
from app.services.totp_debug_service import (
    get_totp_secret,
    provisioning_qr_data_uri,
    totp_allowed_for_user,
    verify_totp,
)
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
            passkeys = list_user_passkeys(db, user_id) if user and passkeys_enabled() else []
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
                    ui.label("Security").classes("text-xl font-black text-slate-950")
                    ui.label(
                        "Use your device's fingerprint, Face ID, Windows Hello, screen lock, or a security key through passkeys. "
                        "Pruvio never receives biometric data."
                    ).classes("text-sm text-slate-500 mt-1")

                    config = passkey_config_summary()
                    if not config["enabled"]:
                        ui.label(
                            "Passkeys are not available yet. Ensure the webauthn dependency and PASSKEY_ENABLED=true are configured."
                        ).classes("text-xs text-amber-700 mt-3")
                    else:
                        device_name = ui.input(
                            "Passkey name",
                            value="My phone / tablet",
                            placeholder="e.g. Bogdan's iPhone",
                        ).props("outlined").classes("w-full mt-4")
                        passkey_status = ui.label("").classes("text-xs text-red-600")

                        async def add_passkey():
                            passkey_status.set_text("")
                            db_begin = SessionLocal()
                            try:
                                current = get_logged_in_user(db_begin)
                                if current is None:
                                    raise ValueError("Your session has expired. Sign in again.")
                                challenge, options_json = begin_passkey_registration(db_begin, current)
                            except Exception as error:
                                passkey_status.set_text(str(error))
                                return
                            finally:
                                db_begin.close()

                            try:
                                browser_result = await ui.run_javascript(
                                    registration_browser_javascript(options_json),
                                    timeout=75.0,
                                )
                            except Exception as error:
                                passkey_status.set_text(str(error) or "Passkey setup was cancelled or failed.")
                                return

                            db_finish = SessionLocal()
                            try:
                                current = get_logged_in_user(db_finish)
                                if current is None:
                                    raise ValueError("Your session has expired. Sign in again.")
                                complete_passkey_registration(
                                    db_finish,
                                    current,
                                    challenge=challenge,
                                    browser_credential=browser_result,
                                    device_name=device_name.value or "Passkey",
                                )
                            except Exception as error:
                                passkey_status.set_text(str(error))
                                return
                            finally:
                                db_finish.close()

                            ui.notify("Passkey added. You can now sign in with this device.", type="positive")
                            ui.navigate.to("/account")

                        ui.button(
                            "Add fingerprint / Face ID / passkey",
                            icon="fingerprint",
                            on_click=add_passkey,
                        ).classes("pruvio-primary w-full mt-2 py-3")
                        ui.label(
                            f"WebAuthn RP: {config['rp_id']} · Origin: {config['origin']}"
                        ).classes("text-[10px] text-slate-400 break-all")

                        ui.separator().classes("my-5")
                        ui.label("Your passkeys").classes("font-black text-slate-900")
                        if not passkeys:
                            ui.label("No passkeys registered yet.").classes("text-sm text-slate-400 mt-2")
                        else:
                            with ui.column().classes("w-full gap-2 mt-2"):
                                for credential in passkeys:
                                    created = credential.created_at.strftime("%d %b %Y")
                                    last_used = (
                                        credential.last_used_at.strftime("%d %b %Y · %H:%M")
                                        if credential.last_used_at
                                        else "Not used yet"
                                    )
                                    with ui.card().classes("pruvio-soft w-full p-4 shadow-none"):
                                        with ui.row().classes("w-full justify-between items-start gap-3"):
                                            with ui.column().classes("gap-0 min-w-0"):
                                                ui.label(credential.device_name or "Passkey").classes("font-black text-slate-900")
                                                ui.label(f"Added {created} · Last used: {last_used}").classes(
                                                    "text-xs text-slate-500"
                                                )
                                                if credential.backed_up:
                                                    ui.label("Synced/backed-up passkey").classes("text-xs text-emerald-700")

                                            def remove_passkey(passkey_id=credential.id):
                                                db_remove = SessionLocal()
                                                try:
                                                    delete_passkey(db_remove, user_id=user_id, passkey_id=passkey_id)
                                                except Exception as error:
                                                    ui.notify(str(error), type="negative")
                                                    return
                                                finally:
                                                    db_remove.close()
                                                ui.notify("Passkey removed.", type="positive")
                                                ui.navigate.to("/account")

                                            ui.button(icon="delete", on_click=remove_passkey).props(
                                                "flat round aria-label='Remove passkey'"
                                            ).classes("text-slate-400")

                    if totp_allowed_for_user(user):
                        ui.separator().classes("my-5")
                        ui.label("Developer Authenticator").classes("font-black text-slate-900")
                        ui.label(
                            "Debug-only TOTP for your allow-listed developer account. It does not test SMS or email delivery."
                        ).classes("text-xs text-slate-500")
                        totp_status = ui.label("").classes("text-xs text-red-600")

                        dialog = ui.dialog()
                        with dialog, ui.card().classes("w-full max-w-md p-6"):
                            ui.label("Set up Authenticator").classes("text-2xl font-black text-slate-950")
                            ui.label(
                                "Scan with Microsoft Authenticator, Google Authenticator, 1Password, Authy, or another TOTP app."
                            ).classes("text-sm text-slate-500")
                            ui.image(provisioning_qr_data_uri(user)).classes("w-64 h-64 self-center my-3")
                            with ui.expansion("Manual setup secret", icon="key").classes("w-full"):
                                ui.label(get_totp_secret(user)).classes("font-mono text-xs break-all select-all")
                            setup_code = ui.input("Current 6-digit code").props(
                                "outlined inputmode=numeric maxlength=6 autocomplete=one-time-code"
                            ).classes("w-full")
                            setup_result = ui.label("").classes("text-xs")

                            def verify_setup():
                                if verify_totp(setup_code.value or "", user=user):
                                    setup_result.classes("text-emerald-700", remove="text-red-600")
                                    setup_result.set_text("Authenticator verified successfully.")
                                else:
                                    setup_result.classes("text-red-600", remove="text-emerald-700")
                                    setup_result.set_text("Code not valid. Check device time and try again.")

                            ui.button("Verify setup", icon="verified", on_click=verify_setup).classes(
                                "pruvio-primary w-full"
                            )
                            ui.button("Close", on_click=dialog.close).props("flat").classes("w-full")

                        ui.button(
                            "Set up / view Authenticator QR",
                            icon="qr_code_2",
                            on_click=dialog.open,
                        ).classes("pruvio-secondary w-full mt-3")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label("Recovery methods").classes("text-lg font-black text-slate-950")
                    ui.label(
                        "Verified email and phone remain your recovery and fallback sign-in methods. Keep both current."
                    ).classes("text-sm text-slate-500 mt-1")
                    with ui.row().classes("gap-2 flex-wrap mt-3"):
                        ui.label("Email OTP ready" if user.is_email_verified else "Email OTP unavailable").classes("metric-pill")
                        ui.label("SMS OTP ready" if user.is_phone_verified else "SMS OTP unavailable").classes("metric-pill")
                    ui.label(
                        "Recovery codes and trusted-device/session management are planned before public launch."
                    ).classes("text-xs text-slate-400 mt-3")

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
                    ui.label("Legal & support").classes("text-lg font-black text-slate-950")
                    with ui.column().classes("w-full gap-2 mt-3"):
                        ui.button("Terms of Use", icon="description", on_click=lambda: ui.navigate.to("/terms")).classes("pruvio-secondary w-full")
                        ui.button("Privacy Notice", icon="privacy_tip", on_click=lambda: ui.navigate.to("/privacy")).classes("pruvio-secondary w-full")
                        ui.button("Help & support", icon="help", on_click=lambda: ui.navigate.to("/support")).classes("pruvio-secondary w-full")
                    ui.label(
                        "Changing verified email/phone and self-service account deletion remain pre-launch work items."
                    ).classes("text-xs text-slate-400 mt-3")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label("Session").classes("text-lg font-black text-slate-950")

                    def sign_out():
                        logout_user()
                        ui.navigate.to("/")

                    ui.button("Sign out", icon="logout", on_click=sign_out).classes("pruvio-secondary mt-3")
        bottom_nav("account")
