from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.split_bill_session_service import list_split_bill_sessions_for_user
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
            split_sessions = list_split_bill_sessions_for_user(db, user_id=user_id, limit=100)
            receipts = list_recent_receipts(db, user_id=user_id, limit=100)
        finally:
            db.close()

        setup_page_head(f"{t('History', lang)} · Pruvs")

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Receipt history", language=lang)

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
                        with ui.column().classes("gap-0"):
                            ui.label("Împărțiri de note" if lang == "ro" else "Split bills").classes(
                                "text-2xl font-black text-slate-950"
                            )
                            ui.label(
                                "Aici apar atât notele deschise, cât și cele finalizate, indiferent dacă ești proprietar sau participant."
                                if lang == "ro"
                                else "Open and settled split bills are kept here whether you are the owner or a participant."
                            ).classes("text-sm text-slate-500")
                        if split_sessions:
                            open_count = sum(1 for row in split_sessions if row["status"] == "open")
                            settled_count = sum(1 for row in split_sessions if row["status"] == "settled")
                            with ui.row().classes("gap-2"):
                                ui.label(f"{open_count} {'deschise' if lang == 'ro' else 'open'}").classes("metric-pill")
                                ui.label(f"{settled_count} {'finalizate' if lang == 'ro' else 'settled'}").classes("metric-pill")

                    if not split_sessions:
                        with ui.column().classes("items-center py-10 gap-2"):
                            ui.icon("group", size="44px").classes("text-slate-300")
                            ui.label("Nu ai încă împărțiri de note." if lang == "ro" else "No split bills yet.").classes(
                                "font-bold text-slate-600"
                            )
                    else:
                        with ui.column().classes("w-full gap-0 mt-3"):
                            for split in split_sessions:
                                created = split["created_at"].strftime("%d %b %Y · %H:%M")
                                is_owner = split["role"] == "owner"
                                status_open = split["status"] == "open"
                                role_label = "Proprietar" if lang == "ro" and is_owner else (
                                    "Participant" if lang == "ro" else ("Owner" if is_owner else "Participant")
                                )
                                status_label = "Deschisă" if lang == "ro" and status_open else (
                                    "Finalizată" if lang == "ro" else ("Open" if status_open else "Settled")
                                )
                                with ui.row().classes(
                                    "item-row w-full items-center justify-between gap-3 py-4 cursor-pointer"
                                ).on("click", lambda _, target=split["widget_url"]: ui.navigate.to(target)):
                                    with ui.column().classes("gap-1 min-w-0 flex-1"):
                                        with ui.row().classes("items-center gap-2 flex-wrap"):
                                            ui.label(f"Split bill #{split['session_id']}").classes(
                                                "font-bold text-slate-900"
                                            )
                                            ui.label(role_label).classes(
                                                "px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-[10px] font-black uppercase tracking-wide"
                                            )
                                            status_classes = (
                                                "px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-black uppercase tracking-wide"
                                                if status_open
                                                else "px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-black uppercase tracking-wide"
                                            )
                                            ui.label(status_label).classes(status_classes)
                                        ui.label(created).classes("text-xs text-slate-400")
                                        if status_open:
                                            ui.label(
                                                f"{'Rămas de împărțit' if lang == 'ro' else 'Remaining to split'}: "
                                                f"{split['remaining_total']:.2f} {split['currency']}"
                                            ).classes("text-xs text-blue-700 font-semibold")
                                        else:
                                            ui.label(
                                                f"{'Partea ta' if lang == 'ro' else 'Your share'}: "
                                                f"{split['my_total']:.2f} {split['currency']}"
                                            ).classes("text-xs text-slate-500")
                                    with ui.column().classes("gap-0 items-end shrink-0"):
                                        ui.label(f"{split['grand_total']:.2f} {split['currency']}").classes(
                                            "font-black text-slate-950 whitespace-nowrap"
                                        )
                                        ui.icon("chevron_right").classes("text-slate-300")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    ui.label(t("Receipt history", lang)).classes("text-2xl font-black text-slate-950")
                    ui.label(
                        "Bonuri procesate în contul tău." if lang == "ro" else "Receipts processed under your account."
                    ).classes("text-sm text-slate-500")
                    if not receipts:
                        with ui.column().classes("items-center py-10 gap-2"):
                            ui.icon("receipt_long", size="44px").classes("text-slate-300")
                            ui.label(t("No receipts yet.", lang)).classes("font-bold text-slate-600")
                    else:
                        with ui.column().classes("w-full gap-0 mt-3"):
                            for receipt in receipts:
                                created = receipt["created_at"].strftime("%d %b %Y · %H:%M")
                                with ui.row().classes(
                                    "item-row w-full items-center justify-between gap-3 py-4 cursor-pointer"
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
        bottom_nav("history", lang)
