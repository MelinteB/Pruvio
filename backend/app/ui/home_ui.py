from nicegui import ui

from app.db.database import SessionLocal
from app.services.auth_service import complete_passwordless_login, start_passwordless_login
from app.services.standalone_app_service import list_recent_receipts
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, login_user


def _login_view() -> None:
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-login-shell gap-6"):
            app_header("Smart receipt assistant", show_account=False)

            with ui.row().classes("w-full items-stretch justify-between gap-6 flex-col lg:flex-row pt-4"):
                with ui.column().classes("flex-1 justify-center gap-4 lg:pr-8"):
                    ui.label("Receipts, simplified.").classes(
                        "text-4xl sm:text-5xl font-black text-slate-950 tracking-tight"
                    )
                    ui.label(
                        "Scan receipts, translate foreign item names, split quantities with friends, "
                        "and keep everything in one private workspace."
                    ).classes("text-base sm:text-lg text-slate-500 max-w-2xl leading-relaxed")
                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.label("Receipt OCR").classes("metric-pill")
                        ui.label("English translation").classes("metric-pill")
                        ui.label("Split bills").classes("metric-pill")
                        ui.label("OTP security").classes("metric-pill metric-accent")

                with ui.card().classes("pruvio-card pruvio-login-card p-6 sm:p-7"):
                    ui.label("Sign in").classes("text-2xl font-black text-slate-950")
                    ui.label("Use your verified email address or phone number.").classes("text-sm text-slate-500")

                    identifier = ui.input("Email or phone number").props(
                        "outlined autocomplete=username"
                    ).classes("w-full mt-3")
                    status = ui.label("").classes("text-xs text-red-600")
                    debug = ui.label("").classes("text-xs text-amber-700")
                    otp_panel = ui.column().classes("w-full gap-3")
                    otp_panel.visible = False

                    with otp_panel:
                        otp = ui.input("6-digit verification code").props(
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

                        ui.button("Verify and sign in", icon="verified_user", on_click=verify_login).classes(
                            "pruvio-primary w-full py-3"
                        )

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
                        status.set_text(f"Verification code sent by {channel} to {destination}.")
                        if result.get("debug_otp"):
                            debug.set_text(f"Local test code: {result['debug_otp']}")

                    ui.button("Continue", icon="login", on_click=send_code).classes(
                        "pruvio-primary w-full py-3"
                    )

                    ui.separator().classes("my-3")
                    with ui.row().classes("w-full justify-center gap-1 text-sm"):
                        ui.label("New to Pruvio?").classes("text-slate-500")
                        ui.label("Create account").classes("pruvio-link").on(
                            "click", lambda: ui.navigate.to("/register")
                        )
                    with ui.row().classes("w-full justify-center gap-3 mt-2"):
                        ui.label("Terms").classes("pruvio-link text-xs").on(
                            "click", lambda: ui.navigate.to("/terms")
                        )
                        ui.label("Privacy").classes("pruvio-link text-xs").on(
                            "click", lambda: ui.navigate.to("/privacy")
                        )
                        ui.label("Help").classes("pruvio-link text-xs").on(
                            "click", lambda: ui.navigate.to("/support")
                        )


def _dashboard(user) -> None:
    db = SessionLocal()
    try:
        recent = list_recent_receipts(db, user_id=user.id, limit=6)
    finally:
        db.close()

    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Smart receipt assistant")

            with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                with ui.column().classes("gap-3"):
                    ui.label(f"Hi, {user.name or 'there'}.").classes(
                        "text-3xl sm:text-4xl font-black text-slate-950 tracking-tight"
                    )
                    ui.label(
                        "Scan a receipt, review the extracted items, split a bill, or open something from your history."
                    ).classes("text-sm sm:text-base text-slate-500 max-w-2xl")
                    with ui.row().classes("gap-3 mt-2 flex-wrap"):
                        ui.button(
                            "Scan or upload receipt",
                            icon="photo_camera",
                            on_click=lambda: ui.navigate.to("/upload"),
                        ).classes("pruvio-primary px-5 py-3")
                        ui.button(
                            "Receipt history",
                            icon="history",
                            on_click=lambda: ui.navigate.to("/history"),
                        ).classes("pruvio-secondary px-5 py-3")

            with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label("Recent receipts").classes("text-lg font-black text-slate-950")
                        ui.label("Your latest processed receipts").classes("text-xs text-slate-500")
                    if recent:
                        ui.label("View all").classes("pruvio-link text-xs").on(
                            "click", lambda: ui.navigate.to("/history")
                        )

                if not recent:
                    with ui.column().classes("w-full items-center py-8 gap-2"):
                        ui.icon("receipt_long", size="42px").classes("text-slate-300")
                        ui.label("No receipts yet.").classes("font-bold text-slate-600")
                        ui.label("Upload your first receipt to start.").classes("text-sm text-slate-400")
                else:
                    with ui.column().classes("w-full gap-0 mt-2"):
                        for receipt in recent:
                            created = receipt["created_at"].strftime("%d %b %Y · %H:%M")
                            with ui.row().classes(
                                "item-row w-full items-center justify-between gap-3 py-3 cursor-pointer"
                            ).on(
                                "click",
                                lambda _, case_id=receipt["case_id"]: ui.navigate.to(f"/receipt/{case_id}"),
                            ):
                                with ui.column().classes("gap-0 min-w-0"):
                                    ui.label(receipt["merchant_name"]).classes("font-bold text-slate-900 truncate")
                                    ui.label(created).classes("text-xs text-slate-400")
                                ui.label(f"{receipt['total']:.2f} {receipt['currency']}").classes(
                                    "font-black text-slate-950 whitespace-nowrap"
                                )
        bottom_nav("home")


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
