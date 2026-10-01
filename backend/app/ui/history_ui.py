from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.standalone_app_service import list_recent_receipts
from app.ui.app_shell import app_header, bottom_nav, setup_page_head
from app.ui.auth_state import get_logged_in_user, require_login


def setup_history_ui() -> None:
    @ui.page("/history")
    def history_page():
        user_id = require_login("/history")
        if user_id is None:
            return
        db = SessionLocal()
        try:
            user = get_logged_in_user(db)
            lang = (user.preferred_language if user else "en") or "en"
            receipts = list_recent_receipts(db, user_id=user_id, limit=100)
        finally:
            db.close()
        setup_page_head(f"{t('History', lang)} · Pruvs")

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Receipt history", language=lang)
                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label(t("Receipt history", lang)).classes("text-2xl font-black text-slate-950")
                    ui.label("Bonuri procesate în contul tău." if lang == "ro" else "Receipts processed under your account.").classes("text-sm text-slate-500")
                    if not receipts:
                        with ui.column().classes("items-center py-10 gap-2"):
                            ui.icon("receipt_long", size="44px").classes("text-slate-300")
                            ui.label(t("No receipts yet.", lang)).classes("font-bold text-slate-600")
                    else:
                        with ui.column().classes("w-full gap-0 mt-3"):
                            for receipt in receipts:
                                created = receipt["created_at"].strftime("%d %b %Y · %H:%M")
                                with ui.row().classes("item-row w-full items-center justify-between gap-3 py-4 cursor-pointer").on(
                                    "click", lambda _, case_id=receipt["case_id"]: ui.navigate.to(f"/receipt/{case_id}"),
                                ):
                                    with ui.column().classes("gap-0 min-w-0"):
                                        ui.label(receipt["merchant_name"]).classes("font-bold text-slate-900 truncate")
                                        ui.label(created).classes("text-xs text-slate-400")
                                    ui.label(f"{receipt['total']:.2f} {receipt['currency']}").classes("font-black text-slate-950 whitespace-nowrap")
        bottom_nav("history", lang)
