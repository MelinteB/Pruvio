from nicegui import ui

from app.db.database import SessionLocal
from app.legal_content import PRIVACY_SECTIONS, PRIVACY_TITLE, TERMS_SECTIONS, TERMS_TITLE
from app.services.onboarding_otp_service import (
    resend_registration_code,
    start_registration,
    verify_registration_email,
    verify_registration_phone,
)
from app.ui.app_shell import app_header, setup_page_head
from app.ui.auth_state import login_user


def _legal_dialog(title: str, sections: list[tuple[str, str]], on_viewed):
    dialog = ui.dialog().props("maximized")
    with dialog, ui.card().classes("w-full h-full p-0"):
        with ui.column().classes("w-full max-w-4xl mx-auto gap-3 p-5 sm:p-8"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(title).classes("text-2xl font-black text-slate-950")
                ui.button(icon="close", on_click=dialog.close).props("flat round")
            ui.label("Draft for product testing. Legal review is required before commercial launch.").classes(
                "text-xs text-amber-700"
            )
            with ui.scroll_area().classes("w-full h-[70vh] pr-2"):
                with ui.column().classes("gap-5"):
                    for heading, body in sections:
                        with ui.column().classes("gap-1"):
                            ui.label(heading).classes("text-base font-black text-slate-900")
                            ui.label(body).classes("text-sm text-slate-600 leading-relaxed")
            ui.button("I have reviewed this document", on_click=lambda: (on_viewed(), dialog.close())).classes(
                "pruvio-primary w-full py-3"
            )
    return dialog


def setup_register_ui() -> None:
    @ui.page("/register")
    def register_page():
        setup_page_head("Create account · Pruvio")
        state = {
            "terms_viewed": False,
            "privacy_viewed": False,
            "user_id": None,
            "phone": None,
            "email": None,
        }

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Create account", show_account=False)

                with ui.card().classes("pruvio-card w-full max-w-2xl mx-auto p-6 sm:p-8"):
                    ui.label("Create your Pruvio account").classes("text-3xl font-black text-slate-950")
                    ui.label(
                        "We verify both your phone number and email address. There is no password to remember."
                    ).classes("text-sm text-slate-500")

                    form_panel = ui.column().classes("w-full gap-3 mt-4")
                    verify_panel = ui.column().classes("w-full gap-4 mt-4")
                    verify_panel.visible = False

                    with form_panel:
                        name = ui.input("Full name").props("outlined autocomplete=name").classes("w-full")
                        email = ui.input("Email address").props("outlined autocomplete=email").classes("w-full")
                        phone = ui.input("Phone number", placeholder="+40 7xx xxx xxx").props(
                            "outlined autocomplete=tel inputmode=tel"
                        ).classes("w-full")

                        with ui.card().classes("pruvio-soft w-full p-4 shadow-none"):
                            ui.label("Legal documents").classes("font-black text-slate-900")
                            ui.label(
                                "You must open both documents before the acceptance boxes become available."
                            ).classes("text-xs text-slate-500")
                            with ui.row().classes("gap-2 mt-2 flex-wrap"):
                                terms_button = ui.button("View Terms of Use", icon="description").classes("pruvio-secondary")
                                privacy_button = ui.button("View Privacy Notice", icon="privacy_tip").classes("pruvio-secondary")

                            terms_check = ui.checkbox("I accept the Terms of Use")
                            privacy_check = ui.checkbox("I acknowledge the Privacy Notice")
                            terms_check.disable()
                            privacy_check.disable()
                            marketing = ui.checkbox("Send me occasional Pruvio product news (optional)")

                        status = ui.label("").classes("text-xs text-red-600")

                        def mark_terms():
                            state["terms_viewed"] = True
                            terms_check.enable()
                            terms_button.props("icon=check_circle")

                        def mark_privacy():
                            state["privacy_viewed"] = True
                            privacy_check.enable()
                            privacy_button.props("icon=check_circle")

                        terms_dialog = _legal_dialog(TERMS_TITLE, TERMS_SECTIONS, mark_terms)
                        privacy_dialog = _legal_dialog(PRIVACY_TITLE, PRIVACY_SECTIONS, mark_privacy)
                        terms_button.on("click", terms_dialog.open)
                        privacy_button.on("click", privacy_dialog.open)

                        debug_phone = ui.label("").classes("text-xs text-amber-700")
                        debug_email = ui.label("").classes("text-xs text-amber-700")

                        def send_registration_codes():
                            status.set_text("")
                            debug_phone.set_text("")
                            debug_email.set_text("")
                            if not state["terms_viewed"] or not state["privacy_viewed"]:
                                status.set_text("Review the Terms and Privacy Notice first.")
                                return
                            if not terms_check.value or not privacy_check.value:
                                status.set_text("Accept the Terms and acknowledge the Privacy Notice to continue.")
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
                                )
                                state["user_id"] = result["user"].id
                                state["phone"] = result["user"].phone_number
                                state["email"] = result["user"].email
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            finally:
                                db.close()

                            if result.get("debug_phone_otp"):
                                debug_phone.set_text(f"Local SMS code: {result['debug_phone_otp']}")
                            if result.get("debug_email_otp"):
                                debug_email.set_text(f"Local email code: {result['debug_email_otp']}")
                            form_panel.visible = False
                            verify_panel.visible = True

                        ui.button("Send verification codes", icon="mark_email_read", on_click=send_registration_codes).classes(
                            "pruvio-primary w-full py-3"
                        )
                        ui.label("Already have an account? Sign in").classes("pruvio-link text-sm self-center").on(
                            "click", lambda: ui.navigate.to("/")
                        )

                    with verify_panel:
                        ui.label("Verify your account").classes("text-2xl font-black text-slate-950")
                        ui.label(
                            "Enter the codes sent separately to your phone and email. Both must be verified."
                        ).classes("text-sm text-slate-500")
                        phone_code = ui.input("SMS code").props(
                            "outlined inputmode=numeric maxlength=6 autocomplete=one-time-code"
                        ).classes("w-full")
                        email_code = ui.input("Email code").props(
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
                            # New accounts go directly to Security so a passkey can be added immediately.
                            ui.navigate.to("/account")

                        ui.button("Verify and create account", icon="verified", on_click=finish_registration).classes(
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
                                        debug_verify.set_text(f"Local {channel} code: {result['debug_otp']}")
                                    ui.notify(f"New {channel} code requested.", type="positive")
                                except Exception as error:
                                    verify_status.set_text(str(error))
                                finally:
                                    db.close()

                            ui.button("Resend SMS", on_click=lambda: resend("phone")).classes("pruvio-secondary flex-1")
                            ui.button("Resend email", on_click=lambda: resend("email")).classes("pruvio-secondary flex-1")
