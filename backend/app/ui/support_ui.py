import os

from nicegui import ui

from app.ui.app_shell import app_header, setup_page_head


def setup_support_ui() -> None:
    @ui.page("/support")
    def support_page():
        setup_page_head("Help · Pruvio")
        support_email = os.getenv("PRUVIO_SUPPORT_EMAIL", "support@pruvio.app")
        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Help & support", show_account=False)
                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label("Help & support").classes("text-3xl font-black text-slate-950")
                    ui.label("Common questions for the current Pruvio test version.").classes("text-sm text-slate-500")
                    faqs = [
                        ("Why do I need two verification codes?", "Pruvio verifies both phone and email during registration so each recovery/contact channel belongs to you."),
                        ("Why can OCR be wrong?", "Receipt extraction and translation are automated. Always review quantities, prices, currency and totals before splitting a bill."),
                        ("Do friends need accounts to join a split?", "No. A participant can use the share link and enter a display name for the current split session."),
                        ("Does Pruvio move money?", "Not in this stage. Pruvio calculates and coordinates amounts; payments are not processed by the current app."),
                        ("How do I protect my account?", "Never share OTP codes. Sign out on shared devices and contact support if you suspect unauthorized access."),
                    ]
                    with ui.column().classes("gap-4 mt-4"):
                        for q, a in faqs:
                            with ui.expansion(q).classes("w-full border border-slate-200 rounded-xl"):
                                ui.label(a).classes("text-sm text-slate-600 p-2")
                    ui.separator().classes("my-5")
                    ui.label("Contact").classes("text-lg font-black text-slate-900")
                    ui.label(support_email).classes("text-sm text-slate-600")
