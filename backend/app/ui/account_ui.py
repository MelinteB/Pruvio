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
    update_payment_details,
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
from app.ui.email_otp_dialog import EmailOTPDialog
from app.ui.otp_recovery import OTPRecovery
from app.services.username_service import update_username
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
        setup_page_head(f"{t('Account', lang)} · Pruvs")

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Account", language=lang)
                recovery = OTPRecovery(f"account:{user_id}", lang)

                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label(user.name or "Pruvs user").classes("text-3xl font-black text-slate-950")
                    ui.label(user.email or ("Fără email" if lang == "ro" else "No email")).classes("text-sm text-slate-500")
                    ui.label("@" + user.username).classes("text-sm font-semibold text-slate-700")
                    ui.label(user.phone_number).classes("text-sm text-slate-500")
                    with ui.row().classes("gap-2 flex-wrap mt-3"):
                        ui.label(t("Email verified" if user.is_email_verified else "Email not verified", lang)).classes(
                            "metric-pill metric-accent" if user.is_email_verified else "metric-pill"
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
                            row = current_account(db_save)
                            update_profile_name(db_save, row, name_input.value or "")
                        except Exception as error:
                            profile_status.set_text(str(error))
                            return
                        finally:
                            db_save.close()
                        profile_status.classes("text-emerald-700", remove="text-red-600")
                        profile_status.set_text("Nume salvat." if lang == "ro" else "Name saved.")

                    ui.button(t("Save name", lang), on_click=save_name).classes("pruvio-secondary")

                    username_input = ui.input("Nume utilizator" if lang == "ro" else "Username", value=user.username).props("outlined maxlength=80").classes("w-full mt-3")
                    def current_account(db):
                        row = get_logged_in_user(db)
                        if not row or row.id != user_id or row.status != "active":
                            raise ValueError("Your session has changed. Sign in again.")
                        return row

                    def save_username():
                        db_save = SessionLocal()
                        try:
                            update_username(db_save, current_account(db_save), username_input.value or "")
                        except Exception as error:
                            profile_status.set_text(str(error))
                            return
                        finally:
                            db_save.close()
                        ui.notify("Nume de utilizator salvat." if lang == "ro" else "Username saved.", type="positive")
                        ui.navigate.to("/account")
                    ui.button("Salvează numele de utilizator" if lang == "ro" else "Save username", on_click=save_username).classes("pruvio-secondary")

                    def contact_editor(channel, label, initial):
                        ui.separator().classes("my-5")
                        value = ui.input(label, value=initial or "").props("outlined autocomplete=" + ("email" if channel == "email" else "tel")).classes("w-full")
                        if channel == "phone":
                            ui.label("Confirmarea telefonului se trimite la emailul verificat." if lang == "ro" else "Confirm phone changes through your verified email.").classes("text-xs text-slate-500")
                        contact_status = ui.label("").classes("text-xs text-red-600")
                        state = {}

                        def request_code(resend=False):
                            db_change = SessionLocal()
                            try:
                                row = current_account(db_change)
                                result = request_contact_change(db_change, row, channel, state["requested_value"] if resend else value.value or "")
                                state.update(result)
                                return result
                            finally:
                                db_change.close()

                        def confirm(code):
                            db_change = SessionLocal()
                            try:
                                row = current_account(db_change)
                                confirm_contact_change(db_change, row, channel, state["requested_value"], code, challenge_id=state["challenge_id"])
                            finally:
                                db_change.close()
                            ui.notify("Contact actualizat." if lang == "ro" else "Contact updated.", type="positive")
                            ui.navigate.to("/account")

                        popup = EmailOTPDialog(title=("Confirmă noul email" if lang == "ro" else "Confirm new email") if channel == "email" else ("Confirmă telefonul" if lang == "ro" else "Confirm phone change"),
                            description=("Introdu codul trimis la noul email." if lang == "ro" else "Enter the code sent to your new email.") if channel == "email" else ("Introdu codul trimis la emailul verificat pentru a salva noul telefon." if lang == "ro" else "Enter the code sent to your verified email to save the new phone number."),
                            on_verify=confirm, on_resend=lambda: request_code(True), language=lang)
                        recovery.field(channel, value)
                        recovery.action(channel, popup, state,
                            ("challenge_id", "requested_value", "destination", "contact_type"))
                        def request_change():
                            contact_status.set_text("")
                            try:
                                popup.present(request_code())
                            except Exception as error:
                                contact_status.set_text(str(error))
                        ui.button(("Schimbă emailul" if lang == "ro" else "Change email") if channel == "email" else ("Schimbă telefonul" if lang == "ro" else "Change phone number"),
                            icon="mail_outline", on_click=request_change).classes("pruvio-secondary")

                    contact_editor("email", t("New email", lang), user.email)
                    contact_editor("phone", t("New phone number", lang), user.phone_number)

                # Password
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label(t("Set / change password", lang)).classes("text-xl font-black text-slate-950")
                    ui.label(
                        "Te poți autentifica prin parolă sau passkey. Dacă ai uitat parola, folosește resetarea prin email."
                        if lang == "ro"
                        else "Sign in with a password or passkey. If you forget your password, reset it by email OTP."
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
                            row = current_account(db_password)
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
                        "Folosește amprenta, Face ID, Windows Hello, blocarea dispozitivului sau o cheie de securitate prin passkey. Pruvs nu primește date biometrice."
                        if lang == "ro"
                        else "Use fingerprint, Face ID, Windows Hello, screen lock, or a security key through passkeys. Pruvs never receives biometric data."
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
                                current = current_account(db_begin)
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
                                current = current_account(db_finish)
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
                                                    current = current_account(db_remove)
                                                    delete_passkey(db_remove, user_id=current.id, passkey_id=passkey_id)
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

                # Payment receiving preferences
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label("Detalii pentru încasări" if lang == "ro" else "Payment details").classes("text-xl font-black text-slate-950")
                    ui.label(
                        "Salvează doar datele pe care vrei să le vadă participanții după finalizarea împărțirii. Plata merge direct către tine; Pruvs nu încasează și nu redirecționează banii."
                        if lang == "ro" else
                        "Save only the details you want participants to see after the split is settled. Payments go directly to you; Pruvs does not collect or redirect the money."
                    ).classes("text-sm text-slate-500")
                    ui.label(
                        "Nu introduce numărul cardului, data expirării, PIN-ul sau CVV-ul."
                        if lang == "ro" else
                        "Do not enter card numbers, expiry dates, PINs or CVV codes."
                    ).classes("text-xs font-semibold text-amber-700 bg-amber-50 rounded-xl px-3 py-2 mt-3")

                    recipient_name = ui.input(
                        "Nume beneficiar" if lang == "ro" else "Recipient name",
                        value=user.payment_recipient_name or "",
                    ).props("outlined").classes("w-full mt-3")
                    iban = ui.input("IBAN", value=user.payment_iban or "").props("outlined autocapitalize=characters").classes("w-full")
                    with ui.row().classes("w-full gap-3 flex-col sm:flex-row"):
                        bank_name = ui.input(
                            "Bancă" if lang == "ro" else "Bank name", value=user.payment_bank_name or ""
                        ).props("outlined").classes("w-full sm:flex-1")
                        bic = ui.input("BIC / SWIFT", value=user.payment_bic or "").props("outlined autocapitalize=characters").classes("w-full sm:flex-1")
                    revolut_link = ui.input(
                        t("Revolut payment link", lang), value=user.revolut_payment_link or ""
                    ).props("outlined placeholder='https://revolut.me/yourname'").classes("w-full")
                    payment_note = ui.input(
                        "Referință / mesaj implicit" if lang == "ro" else "Default payment reference / note",
                        value=user.payment_note or "",
                    ).props("outlined maxlength=255").classes("w-full")
                    ui.label(
                        "Participanții vor vedea aceste date doar după ce nota este finalizată."
                        if lang == "ro" else
                        "Participants will see these details only after the bill is settled."
                    ).classes("text-xs text-slate-400")

                    pay_status = ui.label("").classes("text-xs text-emerald-700")

                    def save_payment_details():
                        db_pay = SessionLocal()
                        try:
                            row = current_account(db_pay)
                            update_payment_details(
                                db_pay,
                                row,
                                recipient_name=recipient_name.value,
                                iban=iban.value,
                                bank_name=bank_name.value,
                                bic=bic.value,
                                revolut_link=revolut_link.value,
                                payment_note=payment_note.value,
                            )
                            pay_status.set_text("Detaliile de plată au fost salvate." if lang == "ro" else "Payment details saved.")
                        except Exception as error:
                            pay_status.set_text(str(error))
                        finally:
                            db_pay.close()

                    ui.button(
                        "Salvează detaliile" if lang == "ro" else "Save payment details",
                        icon="save",
                        on_click=save_payment_details,
                    ).classes("pruvio-secondary mt-2 px-4")

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
                            row = current_account(db_pref)
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
                        "Ștergerea elimină contul și datele asociate din baza de date Pruvs. Confirmarea prin OTP este obligatorie."
                        if lang == "ro"
                        else "Deletion removes your account and associated Pruvs data from the database. OTP confirmation is required."
                    ).classes("text-sm text-slate-500")
                    delete_status = ui.label("").classes("text-xs text-red-600")
                    deletion_state = {}

                    def request_deletion():
                        db_delete = SessionLocal()
                        try:
                            result = request_account_deletion_otp(db_delete, current_account(db_delete), "email")
                            deletion_state.update(result)
                            return result
                        finally:
                            db_delete.close()

                    def delete_account(code):
                        db_delete = SessionLocal()
                        try:
                            confirm_and_delete_account(db_delete, current_account(db_delete), "email", code,
                                challenge_id=deletion_state["challenge_id"])
                        finally:
                            db_delete.close()
                        logout_user()
                        ui.navigate.to("/")

                    deletion_popup = EmailOTPDialog(title="Șterge contul" if lang == "ro" else "Delete your account",
                        description="Confirmă cu codul primit pe email. Contul și datele asociate vor fi șterse definitiv." if lang == "ro" else "Confirm with the code sent to your email. Your account and associated data will be permanently deleted.",
                        on_verify=delete_account, on_resend=request_deletion, language=lang, danger=True,
                        confirm_label=t("Delete permanently", lang))
                    recovery.action("delete", deletion_popup, deletion_state, ("challenge_id",))
                    def request_delete_code():
                        delete_status.set_text("")
                        try:
                            deletion_popup.present(request_deletion())
                        except Exception as error:
                            delete_status.set_text(str(error))
                    ui.button(t("Delete account", lang), icon="delete_forever", on_click=request_delete_code).classes("text-red-700 border border-red-200 rounded-xl font-bold")

                def sign_out():
                    logout_user()
                    ui.navigate.to("/")

                ui.button(t("Sign out", lang), icon="logout", on_click=sign_out).classes("pruvio-secondary")
        recovery.start()
        # PRUVS_6122_ACCOUNT_NOTIFICATIONS
        with ui.card().classes('pruvio-card w-full p-4'):
            ui.label('Device notifications').classes('font-bold text-lg')
            ui.label('Choose which notifications you receive and manage this device.').classes('text-sm text-slate-600')
            ui.button('Notification settings', icon='notifications_active', on_click=lambda: ui.navigate.to('/notifications')).props('outline no-caps')
        bottom_nav("account", lang)
