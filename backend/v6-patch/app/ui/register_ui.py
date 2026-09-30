from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.legal_content import (
    PRIVACY_SECTIONS, PRIVACY_SECTIONS_RO, PRIVACY_TITLE, PRIVACY_TITLE_RO,
    TERMS_SECTIONS, TERMS_SECTIONS_RO, TERMS_TITLE, TERMS_TITLE_RO,
)
from app.services.onboarding_otp_service import (
    resend_registration_code,
    start_registration,
    verify_registration_email,
    verify_registration_phone,
)
from app.ui.app_shell import app_header, setup_page_head
from app.ui.auth_state import get_ui_language, login_user


def _legal_dialog(title: str, sections: list[tuple[str, str]], on_viewed, lang: str):
    dialog = ui.dialog().props("maximized")
    with dialog, ui.card().classes("w-full h-full p-0"):
        with ui.column().classes("w-full max-w-4xl mx-auto gap-3 p-5 sm:p-8"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(title).classes("text-2xl font-black text-slate-950")
                ui.button(icon="close", on_click=dialog.close).props("flat round")
            ui.label(
                "Versiune draft pentru testarea produsului. Este necesară revizuire juridică înainte de lansarea comercială."
                if lang == "ro"
                else "Draft for product testing. Legal review is required before commercial launch."
            ).classes("text-xs text-amber-700")
            with ui.scroll_area().classes("w-full h-[70vh] pr-2"):
                with ui.column().classes("gap-5"):
                    for heading, body in sections:
                        with ui.column().classes("gap-1"):
                            ui.label(heading).classes("text-base font-black text-slate-900")
                            ui.label(body).classes("text-sm text-slate-600 leading-relaxed")
            ui.button(t("I have reviewed this document", lang), on_click=lambda: (on_viewed(), dialog.close())).classes(
                "pruvio-primary w-full py-3"
            )
    return dialog


def setup_register_ui() -> None:
    @ui.page("/register")
    def register_page():
        lang = get_ui_language()
        setup_page_head(f"{t('Create account', lang)} · Pruvio")
        state = {
            "terms_viewed": False,
            "privacy_viewed": False,
            "user_id": None,
            "phone": None,
            "email": None,
            "debug_phone": None,
            "debug_email": None,
        }

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Create account", show_account=False, language=lang)

                with ui.card().classes("pruvio-card w-full max-w-2xl mx-auto p-6 sm:p-8"):
                    ui.label(t("Create your Pruvio account", lang)).classes("text-3xl font-black text-slate-950")
                    ui.label(
                        "Verificăm atât telefonul, cât și adresa de email. Poți folosi apoi parolă, OTP sau passkey pentru autentificare."
                        if lang == "ro"
                        else "We verify both your phone number and email. You can then sign in with password, OTP, or passkey."
                    ).classes("text-sm text-slate-500")

                    form_panel = ui.column().classes("w-full gap-3 mt-4")
                    verify_panel = ui.column().classes("w-full gap-4 mt-4")
                    verify_panel.visible = False

                    with form_panel:
                        name = ui.input(t("Full name", lang)).props("outlined autocomplete=name").classes("w-full")
                        email = ui.input(t("Email address", lang)).props("outlined autocomplete=email").classes("w-full")
                        phone = ui.input(t("Phone number", lang), placeholder="+40 7xx xxx xxx").props(
                            "outlined autocomplete=tel inputmode=tel"
                        ).classes("w-full")
                        password = ui.input(t("Password", lang), password=True, password_toggle_button=True).props(
                            "outlined autocomplete=new-password"
                        ).classes("w-full")
                        confirm_password = ui.input(t("Confirm password", lang), password=True, password_toggle_button=True).props(
                            "outlined autocomplete=new-password"
                        ).classes("w-full")
                        ui.label(
                            "Minimum 8 caractere. Parola poate fi resetată ulterior prin OTP trimis pe email."
                            if lang == "ro"
                            else "Minimum 8 characters. You can later reset it with an OTP sent to your email."
                        ).classes("text-xs text-slate-400")

                        with ui.card().classes("pruvio-soft w-full p-4 shadow-none"):
                            ui.label(t("Legal documents", lang)).classes("font-black text-slate-900")
                            ui.label(
                                "Deschide ambele documente înainte ca opțiunile de acceptare să fie disponibile."
                                if lang == "ro"
                                else "You must open both documents before the acceptance boxes become available."
                            ).classes("text-xs text-slate-500")
                            with ui.row().classes("gap-2 mt-2 flex-wrap"):
                                terms_button = ui.button(t("View Terms of Use", lang), icon="description").classes("pruvio-secondary")
                                privacy_button = ui.button(t("View Privacy Notice", lang), icon="privacy_tip").classes("pruvio-secondary")

                            terms_check = ui.checkbox(t("I accept the Terms of Use", lang))
                            privacy_check = ui.checkbox(t("I acknowledge the Privacy Notice", lang))
                            terms_check.disable()
                            privacy_check.disable()
                            marketing = ui.checkbox(t("Send me occasional Pruvio product news (optional)", lang))

                        status = ui.label("").classes("text-xs text-red-600")

                        def mark_terms():
                            state["terms_viewed"] = True
                            terms_check.enable()
                            terms_button.props("icon=check_circle")

                        def mark_privacy():
                            state["privacy_viewed"] = True
                            privacy_check.enable()
                            privacy_button.props("icon=check_circle")

                        terms_dialog = _legal_dialog(TERMS_TITLE_RO if lang == "ro" else TERMS_TITLE, TERMS_SECTIONS_RO if lang == "ro" else TERMS_SECTIONS, mark_terms, lang)
                        privacy_dialog = _legal_dialog(PRIVACY_TITLE_RO if lang == "ro" else PRIVACY_TITLE, PRIVACY_SECTIONS_RO if lang == "ro" else PRIVACY_SECTIONS, mark_privacy, lang)
                        terms_button.on("click", terms_dialog.open)
                        privacy_button.on("click", privacy_dialog.open)

                        def send_registration_codes():
                            status.set_text("")
                            if not state["terms_viewed"] or not state["privacy_viewed"]:
                                status.set_text("Citește Termenii și Nota de confidențialitate mai întâi." if lang == "ro" else "Review the Terms and Privacy Notice first.")
                                return
                            if not terms_check.value or not privacy_check.value:
                                status.set_text("Acceptă Termenii și Nota de confidențialitate pentru a continua." if lang == "ro" else "Accept the Terms and acknowledge the Privacy Notice to continue.")
                                return
                            if (password.value or "") != (confirm_password.value or ""):
                                status.set_text("Parolele nu coincid." if lang == "ro" else "Passwords do not match.")
                                return
                            db = SessionLocal()
                            try:
                                result = start_registration(
                                    db,
                                    phone_number=phone.value or "",
                                    display_name=name.value or "",
                                    email=email.value or "",
                                    accepted_terms=True,
                                    accepted_privacy=True,
                                    marketing_opt_in=bool(marketing.value),
                                    password=password.value or "",
                                )
                                state["user_id"] = result["user"].id
                                state["phone"] = result["user"].phone_number
                                state["email"] = result["user"].email
                                state["debug_phone"] = result.get("debug_phone_otp")
                                state["debug_email"] = result.get("debug_email_otp")
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            finally:
                                db.close()

                            phone_destination.set_text(
                                f"Cod SMS trimis la: {state['phone']}" if lang == "ro" else f"SMS code sent to: {state['phone']}"
                            )
                            email_destination.set_text(
                                f"Cod email trimis la: {state['email']}" if lang == "ro" else f"Email code sent to: {state['email']}"
                            )
                            debug_phone_label.set_text(f"OTP SMS debug: {state['debug_phone']}" if state.get("debug_phone") else "")
                            debug_email_label.set_text(f"OTP email debug: {state['debug_email']}" if state.get("debug_email") else "")
                            form_panel.visible = False
                            verify_panel.visible = True

                        ui.button(t("Send verification codes", lang), icon="mark_email_read", on_click=send_registration_codes).classes(
                            "pruvio-primary w-full py-3"
                        )
                        ui.label(t("Already have an account? Sign in", lang)).classes("pruvio-link text-sm self-center").on(
                            "click", lambda: ui.navigate.to("/")
                        )

                    with verify_panel:
                        ui.label(t("Verify your account", lang)).classes("text-2xl font-black text-slate-950")
                        ui.label(
                            "Introdu codurile trimise separat la telefon și email. Ambele trebuie verificate."
                            if lang == "ro"
                            else "Enter the codes sent separately to your phone and email. Both must be verified."
                        ).classes("text-sm text-slate-500")

                        phone_destination = ui.label("").classes("text-sm font-bold text-slate-700")
                        email_destination = ui.label("").classes("text-sm font-bold text-slate-700")
                        debug_phone_label = ui.label("").classes("text-xs text-amber-700")
                        debug_email_label = ui.label("").classes("text-xs text-amber-700")

                        phone_code = ui.input(t("SMS code", lang)).props(
                            "outlined inputmode=numeric maxlength=6 autocomplete=one-time-code"
                        ).classes("w-full")
                        email_code = ui.input(t("Email code", lang)).props(
                            "outlined inputmode=numeric maxlength=6 autocomplete=one-time-code"
                        ).classes("w-full")
                        verify_status = ui.label("").classes("text-xs text-red-600")
                        debug_verify = ui.label("").classes("text-xs text-amber-700")

                        def finish_registration():
                            db = SessionLocal()
                            try:
                                user = verify_registration_phone(db, state["phone"], phone_code.value or "")
                                user = verify_registration_email(db, state["email"], email_code.value or "")
                                if user.status != "active":
                                    raise ValueError("Both channels must be verified before the account becomes active.")
                                login_user(user)
                            except Exception as error:
                                verify_status.set_text(str(error))
                                return
                            finally:
                                db.close()
                            ui.navigate.to("/account")

                        ui.button(t("Verify and create account", lang), icon="verified", on_click=finish_registration).classes(
                            "pruvio-primary w-full py-3"
                        )

                        with ui.row().classes("w-full gap-2 flex-wrap"):
                            def resend(channel: str):
                                db = SessionLocal()
                                try:
                                    from app.models.user import User
                                    user = db.query(User).filter(User.id == state["user_id"]).first()
                                    if not user:
                                        raise ValueError("Registration session expired. Start again.")
                                    result = resend_registration_code(db, user, channel)
                                    if result.get("debug_otp"):
                                        debug_verify.set_text(f"OTP debug {channel}: {result['debug_otp']}")
                                    ui.notify(
                                        f"Cod nou trimis prin {channel}." if lang == "ro" else f"New {channel} code requested.",
                                        type="positive",
                                    )
                                except Exception as error:
                                    verify_status.set_text(str(error))
                                finally:
                                    db.close()

                            ui.button(t("Resend SMS", lang), on_click=lambda: resend("phone")).classes("pruvio-secondary flex-1")
                            ui.button(t("Resend email", lang), on_click=lambda: resend("email")).classes("pruvio-secondary flex-1")
