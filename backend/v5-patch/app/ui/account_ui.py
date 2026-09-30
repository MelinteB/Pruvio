from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.models.user import User
from app.services.account_service import (
    confirm_and_delete_account,
    confirm_contact_change,
    request_account_deletion_otp,
    request_contact_change,
    set_password,
    update_preferences,
    update_profile_name,
)
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
from app.ui.auth_state import (
    get_logged_in_user,
    logout_user,
    require_login,
    set_ui_language,
)


def setup_account_ui() -> None:
    @ui.page("/account")
    def account_page():
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

        lang = user.preferred_language or "en"
        setup_page_head(f"{t('Account', lang)} · Pruvio")

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Account", language=lang)

                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label(user.name or "Pruvio user").classes("text-3xl font-black text-slate-950")
                    ui.label(user.email or ("Fără email" if lang == "ro" else "No email")).classes("text-sm text-slate-500")
                    ui.label(user.phone_number).classes("text-sm text-slate-500")
                    with ui.row().classes("gap-2 flex-wrap mt-3"):
                        ui.label(t("Email verified" if user.is_email_verified else "Email not verified", lang)).classes(
                            "metric-pill metric-accent" if user.is_email_verified else "metric-pill"
                        )
                        ui.label(t("Phone verified" if user.is_phone_verified else "Phone not verified", lang)).classes(
                            "metric-pill metric-accent" if user.is_phone_verified else "metric-pill"
                        )
                        ui.label(t("Active account", lang) if user.status == "active" else user.status).classes("metric-pill")

                # Profile details
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label(t("Profile", lang)).classes("text-xl font-black text-slate-950")
                    name_input = ui.input(t("Name", lang), value=user.name or "").props("outlined").classes("w-full mt-3")
                    profile_status = ui.label("").classes("text-xs text-red-600")

                    def save_name():
                        db_save = SessionLocal()
                        try:
                            row = db_save.query(User).filter(User.id == user_id).first()
                            update_profile_name(db_save, row, name_input.value or "")
                        except Exception as error:
                            profile_status.set_text(str(error))
                            return
                        finally:
                            db_save.close()
                        profile_status.classes("text-emerald-700", remove="text-red-600")
                        profile_status.set_text("Nume salvat." if lang == "ro" else "Name saved.")

                    ui.button(t("Save name", lang), on_click=save_name).classes("pruvio-secondary")

                    ui.separator().classes("my-5")
                    ui.label(t("Current email", lang)).classes("text-xs font-bold text-slate-500")
                    ui.label(user.email or "—").classes("text-sm font-black text-slate-900")
                    new_email = ui.input(t("New email", lang), value=user.email or "").props("outlined autocomplete=email").classes("w-full")
                    email_otp = ui.input(t("Email code", lang)).props("outlined inputmode=numeric maxlength=6").classes("w-full")
                    email_status = ui.label("").classes("text-xs text-slate-500")
                    email_debug = ui.label("").classes("text-xs text-amber-700")

                    def request_email_change():
                        db_change = SessionLocal()
                        try:
                            row = db_change.query(User).filter(User.id == user_id).first()
                            result = request_contact_change(db_change, row, "email", new_email.value or "")
                        except Exception as error:
                            email_status.set_text(str(error))
                            return
                        finally:
                            db_change.close()
                        email_status.set_text(
                            f"OTP trimis la {result['destination']}." if lang == "ro" else f"OTP sent to {result['destination']}."
                        )
                        email_debug.set_text(f"OTP debug: {result['debug_otp']}" if result.get("debug_otp") else "")

                    def confirm_email_change():
                        db_change = SessionLocal()
                        try:
                            row = db_change.query(User).filter(User.id == user_id).first()
                            confirm_contact_change(db_change, row, "email", new_email.value or "", email_otp.value or "")
                        except Exception as error:
                            email_status.set_text(str(error))
                            return
                        finally:
                            db_change.close()
                        ui.notify("Email actualizat și verificat." if lang == "ro" else "Email updated and verified.", type="positive")
                        ui.navigate.to("/account")

                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button(t("Send email OTP", lang), icon="mail", on_click=request_email_change).classes("pruvio-secondary")
                        ui.button(t("Confirm email change", lang), icon="verified", on_click=confirm_email_change).classes("pruvio-primary")

                    ui.separator().classes("my-5")
                    ui.label(t("Current phone", lang)).classes("text-xs font-bold text-slate-500")
                    ui.label(user.phone_number or "—").classes("text-sm font-black text-slate-900")
                    new_phone = ui.input(t("New phone number", lang), value=user.phone_number or "").props("outlined autocomplete=tel").classes("w-full")
                    phone_otp = ui.input(t("SMS code", lang)).props("outlined inputmode=numeric maxlength=6").classes("w-full")
                    phone_status = ui.label("").classes("text-xs text-slate-500")
                    phone_debug = ui.label("").classes("text-xs text-amber-700")

                    def request_phone_change():
                        db_change = SessionLocal()
                        try:
                            row = db_change.query(User).filter(User.id == user_id).first()
                            result = request_contact_change(db_change, row, "phone", new_phone.value or "")
                        except Exception as error:
                            phone_status.set_text(str(error))
                            return
                        finally:
                            db_change.close()
                        phone_status.set_text(
                            f"OTP trimis la {result['destination']}." if lang == "ro" else f"OTP sent to {result['destination']}."
                        )
                        phone_debug.set_text(f"OTP debug: {result['debug_otp']}" if result.get("debug_otp") else "")

                    def confirm_phone_change():
                        db_change = SessionLocal()
                        try:
                            row = db_change.query(User).filter(User.id == user_id).first()
                            confirm_contact_change(db_change, row, "phone", new_phone.value or "", phone_otp.value or "")
                        except Exception as error:
                            phone_status.set_text(str(error))
                            return
                        finally:
                            db_change.close()
                        ui.notify("Telefon actualizat și verificat." if lang == "ro" else "Phone updated and verified.", type="positive")
                        ui.navigate.to("/account")

                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button(t("Send phone OTP", lang), icon="sms", on_click=request_phone_change).classes("pruvio-secondary")
                        ui.button(t("Confirm phone change", lang), icon="verified", on_click=confirm_phone_change).classes("pruvio-primary")

                # Password
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label(t("Set / change password", lang)).classes("text-xl font-black text-slate-950")
                    ui.label(
                        "Poți folosi parola împreună cu OTP și passkey. Dacă ai uitat parola, folosește resetarea prin email."
                        if lang == "ro"
                        else "Password is available alongside OTP and passkeys. If you forget it, reset it by email OTP."
                    ).classes("text-sm text-slate-500")
                    current_password = ui.input(t("Current password", lang), password=True, password_toggle_button=True).props("outlined").classes("w-full mt-3")
                    new_password = ui.input(t("New password", lang), password=True, password_toggle_button=True).props("outlined").classes("w-full")
                    confirm_password = ui.input(t("Confirm new password", lang), password=True, password_toggle_button=True).props("outlined").classes("w-full")
                    password_status = ui.label("").classes("text-xs text-red-600")

                    def save_password():
                        if (new_password.value or "") != (confirm_password.value or ""):
                            password_status.set_text("Parolele nu coincid." if lang == "ro" else "Passwords do not match.")
                            return
                        db_password = SessionLocal()
                        try:
                            row = db_password.query(User).filter(User.id == user_id).first()
                            set_password(db_password, row, new_password.value or "", current_password.value or None)
                        except Exception as error:
                            password_status.set_text(str(error))
                            return
                        finally:
                            db_password.close()
                        ui.notify("Parola a fost salvată." if lang == "ro" else "Password saved.", type="positive")
                        current_password.value = ""
                        new_password.value = ""
                        confirm_password.value = ""

                    ui.button(t("Set / change password", lang), icon="password", on_click=save_password).classes("pruvio-primary mt-2")
                    ui.label(t("Forgot password?", lang)).classes("pruvio-link text-xs mt-2").on("click", lambda: ui.navigate.to("/reset-password"))

                # Passkeys and TOTP
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label(t("Security", lang)).classes("text-xl font-black text-slate-950")
                    ui.label(
                        "Folosește amprenta, Face ID, Windows Hello, blocarea dispozitivului sau o cheie de securitate prin passkey. Pruvio nu primește date biometrice."
                        if lang == "ro"
                        else "Use fingerprint, Face ID, Windows Hello, screen lock, or a security key through passkeys. Pruvio never receives biometric data."
                    ).classes("text-sm text-slate-500 mt-1")

                    config = passkey_config_summary()
                    if not config["enabled"]:
                        ui.label("Passkey-urile nu sunt disponibile încă." if lang == "ro" else "Passkeys are not available yet.").classes("text-xs text-amber-700 mt-3")
                    else:
                        device_name = ui.input("Nume passkey" if lang == "ro" else "Passkey name", value="Telefon / tabletă" if lang == "ro" else "My phone / tablet").props("outlined").classes("w-full mt-4")
                        passkey_status = ui.label("").classes("text-xs text-red-600")

                        async def add_passkey():
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
                                browser_result = await ui.run_javascript(registration_browser_javascript(options_json), timeout=75.0)
                            except Exception as error:
                                passkey_status.set_text(str(error) or "Passkey setup failed.")
                                return
                            db_finish = SessionLocal()
                            try:
                                current = get_logged_in_user(db_finish)
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
                            ui.notify("Passkey adăugat." if lang == "ro" else "Passkey added.", type="positive")
                            ui.navigate.to("/account")

                        ui.button(t("Use fingerprint / Face ID / passkey", lang), icon="fingerprint", on_click=add_passkey).classes("pruvio-primary w-full mt-2 py-3")
                        ui.label(f"WebAuthn RP: {config['rp_id']} · Origin: {config['origin']}").classes("text-[10px] text-slate-400 break-all")

                        ui.separator().classes("my-5")
                        ui.label("Passkey-urile tale" if lang == "ro" else "Your passkeys").classes("font-black text-slate-900")
                        if not passkeys:
                            ui.label("Niciun passkey înregistrat." if lang == "ro" else "No passkeys registered yet.").classes("text-sm text-slate-400 mt-2")
                        else:
                            with ui.column().classes("w-full gap-2 mt-2"):
                                for credential in passkeys:
                                    with ui.card().classes("pruvio-soft w-full p-4 shadow-none"):
                                        with ui.row().classes("w-full justify-between items-start gap-3"):
                                            ui.label(credential.device_name or "Passkey").classes("font-black text-slate-900")

                                            def remove_passkey(passkey_id=credential.id):
                                                db_remove = SessionLocal()
                                                try:
                                                    delete_passkey(db_remove, user_id=user_id, passkey_id=passkey_id)
                                                finally:
                                                    db_remove.close()
                                                ui.navigate.to("/account")

                                            ui.button(icon="delete", on_click=remove_passkey).props("flat round")

                    if totp_allowed_for_user(user):
                        ui.separator().classes("my-5")
                        ui.label(t("Developer Authenticator", lang)).classes("font-black text-slate-900")
                        dialog = ui.dialog()
                        with dialog, ui.card().classes("w-full max-w-md p-6"):
                            ui.label("Configurare Authenticator" if lang == "ro" else "Set up Authenticator").classes("text-2xl font-black text-slate-950")
                            ui.image(provisioning_qr_data_uri(user)).classes("w-64 h-64 self-center my-3")
                            with ui.expansion("Cheie manuală" if lang == "ro" else "Manual setup secret", icon="key").classes("w-full"):
                                ui.label(get_totp_secret(user)).classes("font-mono text-xs break-all select-all")
                            setup_code = ui.input(t("Authenticator code", lang)).props("outlined inputmode=numeric maxlength=6").classes("w-full")
                            setup_result = ui.label("").classes("text-xs")

                            def verify_setup():
                                ok = verify_totp(setup_code.value or "", user=user)
                                setup_result.set_text(("Cod valid." if lang == "ro" else "Authenticator verified successfully.") if ok else ("Cod invalid." if lang == "ro" else "Code not valid."))

                            ui.button(t("Verify Authenticator", lang), on_click=verify_setup).classes("pruvio-primary w-full")
                            ui.button("Închide" if lang == "ro" else "Close", on_click=dialog.close).props("flat").classes("w-full")
                        ui.button("Configurează / vezi QR Authenticator" if lang == "ro" else "Set up / view Authenticator QR", icon="qr_code_2", on_click=dialog.open).classes("pruvio-secondary w-full mt-3")

                # Preferences
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label(t("Preferences", lang)).classes("text-xl font-black text-slate-950")
                    language = ui.select({"en": "English", "ro": "Română"}, value=lang, label=t("Preferred language", lang)).props("outlined").classes("w-full mt-3")
                    notifications = ui.checkbox(t("Product notifications", lang), value=bool(user.notifications_opt_in))
                    marketing = ui.checkbox(t("Marketing messages", lang), value=bool(user.marketing_opt_in))
                    preference_status = ui.label("").classes("text-xs text-emerald-700")

                    def save_preferences():
                        db_pref = SessionLocal()
                        try:
                            row = db_pref.query(User).filter(User.id == user_id).first()
                            update_preferences(
                                db_pref,
                                row,
                                preferred_language=language.value or "en",
                                notifications_opt_in=bool(notifications.value),
                                marketing_opt_in=bool(marketing.value),
                            )
                        except Exception as error:
                            preference_status.set_text(str(error))
                            return
                        finally:
                            db_pref.close()
                        set_ui_language(language.value or "en")
                        ui.navigate.to("/account")

                    ui.button(t("Save preferences", lang), on_click=save_preferences).classes("pruvio-primary mt-3")

                # Legal/support/session
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    with ui.column().classes("w-full gap-2"):
                        ui.button(t("Terms of Use", lang), icon="description", on_click=lambda: ui.navigate.to("/terms")).classes("pruvio-secondary w-full")
                        ui.button(t("Privacy Notice", lang), icon="privacy_tip", on_click=lambda: ui.navigate.to("/privacy")).classes("pruvio-secondary w-full")
                        ui.button(t("Help & Support", lang), icon="help", on_click=lambda: ui.navigate.to("/support")).classes("pruvio-secondary w-full")

                # Delete account
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6 border-red-200"):
                    ui.label(t("Delete account", lang)).classes("text-xl font-black text-red-700")
                    ui.label(
                        "Ștergerea elimină contul și datele asociate din baza de date Pruvio. Confirmarea prin OTP este obligatorie."
                        if lang == "ro"
                        else "Deletion removes your account and associated Pruvio data from the database. OTP confirmation is required."
                    ).classes("text-sm text-slate-500")
                    channel = ui.select({"email": "Email", "phone": "SMS"}, value="email" if user.email else "phone", label="Canal OTP" if lang == "ro" else "OTP channel").props("outlined").classes("w-full mt-3")
                    delete_code = ui.input("Cod OTP" if lang == "ro" else "OTP code").props("outlined inputmode=numeric maxlength=6").classes("w-full")
                    delete_status = ui.label("").classes("text-xs text-red-600")
                    delete_debug = ui.label("").classes("text-xs text-amber-700")

                    def request_delete_code():
                        db_delete = SessionLocal()
                        try:
                            row = db_delete.query(User).filter(User.id == user_id).first()
                            result = request_account_deletion_otp(db_delete, row, channel.value)
                        except Exception as error:
                            delete_status.set_text(str(error))
                            return
                        finally:
                            db_delete.close()
                        delete_status.set_text(
                            f"OTP trimis la {result['destination']}." if lang == "ro" else f"OTP sent to {result['destination']}."
                        )
                        delete_debug.set_text(f"OTP debug: {result['debug_otp']}" if result.get("debug_otp") else "")

                    def delete_account():
                        db_delete = SessionLocal()
                        try:
                            row = db_delete.query(User).filter(User.id == user_id).first()
                            confirm_and_delete_account(db_delete, row, channel.value, delete_code.value or "")
                        except Exception as error:
                            delete_status.set_text(str(error))
                            return
                        finally:
                            db_delete.close()
                        logout_user()
                        ui.navigate.to("/")

                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button(t("Request deletion OTP", lang), icon="sms", on_click=request_delete_code).classes("pruvio-secondary")
                        ui.button(t("Delete permanently", lang), icon="delete_forever", on_click=delete_account).classes("bg-red-700 text-white rounded-xl font-bold")

                def sign_out():
                    logout_user()
                    ui.navigate.to("/")

                ui.button(t("Sign out", lang), icon="logout", on_click=sign_out).classes("pruvio-secondary")
        bottom_nav("account", lang)
