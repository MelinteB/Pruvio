from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.account_service import confirm_password_reset, request_password_reset
from app.ui.app_shell import app_header, setup_page_head
from app.ui.auth_state import get_ui_language


def setup_password_reset_ui() -> None:
    @ui.page("/reset-password")
    def reset_password_page():
        lang = get_ui_language()
        setup_page_head(f"{t('Reset password', lang)} · Pruvio")
        state = {"email": None}

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header(t("Reset password", lang), show_account=False, language=lang)
                with ui.card().classes("pruvio-card w-full max-w-xl mx-auto p-6 sm:p-8"):
                    ui.label(t("Reset password", lang)).classes("text-3xl font-black text-slate-950")
                    ui.label(
                        "Vom trimite un cod OTP la adresa ta de email verificată."
                        if lang == "ro"
                        else "We will send an OTP to your verified email address."
                    ).classes("text-sm text-slate-500")
                    email = ui.input(t("Email address", lang)).props("outlined autocomplete=email").classes("w-full mt-3")
                    status = ui.label("").classes("text-xs text-red-600")
                    debug = ui.label("").classes("text-xs text-amber-700")
                    confirm_panel = ui.column().classes("w-full gap-3")
                    confirm_panel.visible = False

                    def send_code():
                        status.set_text("")
                        debug.set_text("")
                        db = SessionLocal()
                        try:
                            result = request_password_reset(db, email.value or "")
                            state["email"] = result["destination"]
                        except Exception as error:
                            status.set_text(str(error))
                            return
                        finally:
                            db.close()
                        status.classes("text-emerald-700", remove="text-red-600")
                        status.set_text(
                            f"Cod trimis la {result['destination']}." if lang == "ro" else f"Code sent to {result['destination']}."
                        )
                        if result.get("debug_otp"):
                            debug.set_text(f"OTP debug: {result['debug_otp']}")
                        confirm_panel.visible = True

                    ui.button(t("Send reset code", lang), icon="mail", on_click=send_code).classes("pruvio-primary w-full py-3")

                    with confirm_panel:
                        code = ui.input(t("Reset code", lang)).props("outlined inputmode=numeric maxlength=6").classes("w-full")
                        new_password = ui.input(t("New password", lang), password=True, password_toggle_button=True).props("outlined").classes("w-full")
                        confirm_password = ui.input(t("Confirm new password", lang), password=True, password_toggle_button=True).props("outlined").classes("w-full")

                        def save_password():
                            if (new_password.value or "") != (confirm_password.value or ""):
                                status.set_text("Parolele nu coincid." if lang == "ro" else "Passwords do not match.")
                                return
                            db = SessionLocal()
                            try:
                                confirm_password_reset(db, state["email"] or email.value or "", code.value or "", new_password.value or "")
                            except Exception as error:
                                status.set_text(str(error))
                                return
                            finally:
                                db.close()
                            ui.notify("Parola a fost actualizată." if lang == "ro" else "Password updated.", type="positive")
                            ui.navigate.to("/")

                        ui.button(t("Save new password", lang), icon="lock_reset", on_click=save_password).classes("pruvio-primary w-full py-3")

                    ui.label(t("Back to sign in", lang)).classes("pruvio-link text-sm self-center mt-2").on("click", lambda: ui.navigate.to("/"))
