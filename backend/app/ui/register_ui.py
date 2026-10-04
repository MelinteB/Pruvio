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
)
from app.ui.auth_state import login_user
from app.ui.email_otp_dialog import EmailOTPDialog
from app.ui.otp_recovery import OTPRecovery
from app.services.username_service import derive_available_username
from app.models.user import User
from app.ui.app_shell import app_header, setup_page_head
from app.ui.auth_state import get_ui_language


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
        setup_page_head(f"{t('Create account', lang)} · Pruvs")
        state = {
            "terms_viewed": False,
            "privacy_viewed": False,
            "user_id": None,
            "email": None,
            "challenge_id": None,
        }

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Create account", show_account=False, language=lang)

                with ui.card().classes("pruvio-card w-full max-w-2xl mx-auto p-6 sm:p-8"):
                    ui.label(t("Create your Pruvs account", lang)).classes("text-3xl font-black text-slate-950")
                    ui.label(
                        "Verificăm adresa de email. Telefonul este folosit doar ca informație de contact. Autentificarea folosește numele de utilizator sau emailul."
                        if lang == "ro"
                        else "We verify your email. Your phone is contact information. Sign in using your unique username or email."
                    ).classes("text-sm text-slate-500")

                    recovery = OTPRecovery("registration", lang)
                    form_panel = ui.column().classes("w-full gap-3 mt-4")

                    with form_panel:
                        with ui.row().classes("w-full gap-3 flex-col sm:flex-row"):
                            first_name = ui.input("Prenume" if lang == "ro" else "First name").props(
                                "outlined autocomplete=given-name"
                            ).classes("w-full")
                            last_name = ui.input("Nume" if lang == "ro" else "Surname").props(
                                "outlined autocomplete=family-name"
                            ).classes("w-full")

                        username = ui.input("Nume utilizator" if lang == "ro" else "Username").props(
                            "outlined readonly autocomplete=username maxlength=80"
                        ).classes("w-full")
                        username_note = ui.label(
                            "Numele de utilizator este creat automat din prenume și nume (ex. ana.popescu)."
                            if lang == "ro" else
                            "Your username is created automatically from your first name and surname (for example ana.popescu)."
                        ).classes("text-xs text-slate-500")

                        def refresh_username_preview(_event=None):
                            first = " ".join((first_name.value or "").split())
                            last = " ".join((last_name.value or "").split())
                            if not first or not last:
                                username.set_value("")
                                return
                            db_check = SessionLocal()
                            try:
                                candidate = derive_available_username(
                                    db_check,
                                    f"{first} {last}",
                                    exclude_user_id=state["user_id"],
                                )
                                username.set_value(candidate)
                                username_note.set_text(
                                    f"Numele tău de utilizator va fi: {candidate}"
                                    if lang == "ro" else
                                    f"Your username will be: {candidate}"
                                )
                            except ValueError as error:
                                username.set_value("")
                                username_note.set_text(str(error))
                            finally:
                                db_check.close()

                        first_name.on_value_change(refresh_username_preview)
                        last_name.on_value_change(refresh_username_preview)
                        email = ui.input(t("Email address", lang)).props("outlined autocomplete=email").classes("w-full")
                        phone = ui.input("Telefon (doar contact)" if lang == "ro" else "Phone number (contact only)", placeholder="+40 7xx xxx xxx").props(
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
                            marketing = ui.checkbox(t("Send me occasional Pruvs product news (optional)", lang))

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
                            first = " ".join((first_name.value or "").split())
                            last = " ".join((last_name.value or "").split())
                            if not first or not last:
                                status.set_text(
                                    "Completează prenumele și numele."
                                    if lang == "ro" else
                                    "Enter both your first name and surname."
                                )
                                return
                            full_name = f"{first} {last}"
                            db = SessionLocal()
                            try:
                                result = start_registration(
                                    db,
                                    phone_number=phone.value or "",
                                    display_name=full_name,
                                    email=email.value or "",
                                    accepted_terms=True,
                                    accepted_privacy=True,
                                    marketing_opt_in=bool(marketing.value),
                                    password=password.value or "",
                                    username=None,
                                )
                                state["user_id"] = result["user"].id
                                state["email"] = result["user"].email
                                state["challenge_id"] = result["challenge_id"]
                                username.set_value(result["user"].username or username.value or "")
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            finally:
                                db.close()

                            try:
                                otp_dialog.present({"destination": state["email"], "delivery": result["email_delivery"], "debug_otp": result.get("debug_email_otp")})
                            except ValueError as error:
                                status.set_text(str(error))

                        ui.button("Creează contul" if lang == "ro" else "Create account", icon="mark_email_read", on_click=send_registration_codes).classes(
                            "pruvio-primary w-full py-3"
                        )
                        ui.label(t("Already have an account? Sign in", lang)).classes("pruvio-link text-sm self-center").on(
                            "click", lambda: ui.navigate.to("/")
                        )

                    async def finish_registration(code):
                        db = SessionLocal()
                        try:
                            if not state.get("challenge_id") or not state.get("email"):
                                raise ValueError("Registration session expired. Request a new code.")
                            # A recovered page must ALWAYS prove the OTP. Never treat an
                            # already-verified account or a saved user ID as authentication.
                            user = verify_registration_email(db, state["email"], code, challenge_id=state["challenge_id"])
                            if user.status != "active":
                                raise ValueError("Verify your email to activate this account.")
                            target = login_user(user)
                        finally:
                            db.close()
                        ui.navigate.to(target if target != "/" else "/account")

                    def resend():
                        db = SessionLocal()
                        try:
                            user = db.get(User, state["user_id"])
                            if not user:
                                raise ValueError("Registration session expired. Start again.")
                            result = resend_registration_code(db, user, "email")
                            state["challenge_id"] = result["challenge_id"]
                            result["destination"] = user.email
                            return result
                        finally:
                            db.close()

                    otp_dialog = EmailOTPDialog(title="Verifică emailul" if lang == "ro" else "Verify your email",
                        description="Introdu codul pentru a activa contul." if lang == "ro" else "Enter the code to activate your account.",
                        on_verify=finish_registration, on_resend=resend, language=lang,
                        confirm_label="Verifică și creează contul" if lang == "ro" else "Verify and create account")

                    recovery.action("registration", otp_dialog, state,
                        ("user_id", "email", "challenge_id", "terms_viewed", "privacy_viewed"))
                    for key, element in (("first_name", first_name), ("last_name", last_name),
                                         ("email", email), ("phone", phone),
                                         ("terms", terms_check), ("privacy", privacy_check),
                                         ("marketing", marketing)):
                        recovery.field(key, element)
                    def restore_form():
                        if terms_check.value: mark_terms()
                        if privacy_check.value: mark_privacy()
                    recovery.start(restore_form)
