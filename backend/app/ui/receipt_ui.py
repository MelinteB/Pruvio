from nicegui import ui

from app.db.database import SessionLocal
from app.services.split_bill_session_service import (
    create_split_bill_session,
    get_owner_participant,
)
from app.services.standalone_app_service import get_receipt_view
from app.ui.app_shell import (
    app_header,
    bottom_nav,
    display_item_name,
    is_integer_quantity,
    quantity_text,
    setup_page_head,
)
from app.ui.auth_state import require_login


def setup_receipt_ui() -> None:
    @ui.page("/receipt/{case_id}")
    def receipt_page(case_id: int):
        setup_page_head("Receipt · Pruvio")

        user_id = require_login(f"/receipt/{case_id}")
        if user_id is None:
            return

        db = SessionLocal()
        try:
            receipt = get_receipt_view(db, case_id, user_id=user_id)
        finally:
            db.close()

        if not receipt:
            with ui.element("main").classes("pruvio-page"):
                with ui.column().classes("pruvio-shell gap-4"):
                    app_header("Receipt")
                    with ui.card().classes("pruvio-card w-full p-6"):
                        ui.label("Receipt not found.").classes("text-xl font-black")
            return

        items = receipt["items"]
        currency = receipt["currency"]
        total_units = 0
        for item in items:
            quantity = float(item["quantity"] or 1)
            total_units += int(round(quantity)) if is_integer_quantity(quantity) else 1

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Receipt review")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    with ui.row().classes("w-full items-start justify-between gap-4 flex-col sm:flex-row"):
                        with ui.column().classes("gap-1"):
                            ui.label(receipt["merchant_name"]).classes(
                                "text-2xl sm:text-3xl font-black text-slate-950"
                            )
                            if receipt.get("original_filename"):
                                ui.label(receipt["original_filename"]).classes("text-xs text-slate-400")
                        with ui.column().classes("gap-0 sm:items-end"):
                            ui.label(f"{receipt['receipt_total']:.2f} {currency}").classes(
                                "text-3xl font-black text-slate-950"
                            )
                            ui.label(f"{len(items)} lines · {total_units} units").classes(
                                "text-xs font-bold text-slate-500"
                            )

                with ui.card().classes("pruvio-card w-full p-0 overflow-hidden"):
                    with ui.row().classes("w-full items-center justify-between px-5 py-4 border-b border-slate-100"):
                        with ui.column().classes("gap-0"):
                            ui.label("Items").classes("text-lg font-black text-slate-950")
                            ui.label("Original receipt text with English translation when needed").classes("text-xs text-slate-500")

                    if not items:
                        ui.label("No receipt items were extracted.").classes("p-5 text-slate-500")
                    else:
                        with ui.column().classes("w-full gap-0"):
                            for item in items:
                                quantity = float(item["quantity"] or 1)
                                unit_price = float(item["unit_price"] or 0)
                                with ui.row().classes("item-row w-full items-center justify-between gap-4 px-5 py-4"):
                                    with ui.column().classes("gap-1 min-w-0 flex-1"):
                                        ui.label(display_item_name(item)).classes(
                                            "text-sm sm:text-base font-bold text-slate-950 leading-snug"
                                        )
                                        detail = (
                                            f"{quantity_text(quantity)} × {unit_price:.2f} {item['currency']} each"
                                            if is_integer_quantity(quantity) and quantity > 1
                                            else f"{quantity_text(quantity)} unit · {unit_price:.2f} {item['currency']}"
                                        )
                                        ui.label(detail).classes("text-xs text-slate-500")
                                    ui.label(
                                        f"{item['total_price']:.2f} {item['currency']}"
                                    ).classes("text-sm sm:text-base font-black text-slate-950 whitespace-nowrap")

                with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                    with ui.row().classes("w-full items-end justify-between gap-4 flex-col sm:flex-row"):
                        with ui.column().classes("gap-1"):
                            ui.label("Split this bill").classes("text-lg font-black text-slate-950")
                            ui.label(
                                "Choose the total number of people, including you. Friends join with a simple link and name."
                            ).classes("text-xs text-slate-500 max-w-xl")

                        participant_count = ui.number(
                            label="People",
                            value=2,
                            min=1,
                            max=20,
                            step=1,
                        ).props("outlined dense").classes("w-32")

                    def start_split():
                        try:
                            expected = int(participant_count.value or 2)
                        except (TypeError, ValueError):
                            expected = 2

                        db_split = SessionLocal()
                        try:
                            session = create_split_bill_session(
                                db=db_split,
                                case_id=case_id,
                                owner_user_id=receipt["user_id"],
                                expected_participants_count=expected,
                            )
                            owner = get_owner_participant(db_split, session)
                            if not owner:
                                raise ValueError("Could not create the bill owner participant.")
                            target = (
                                f"/split-bill/sessions/{session.token}/widget-ui"
                                f"?participant_id={owner.id}"
                            )
                        except Exception as error:
                            ui.notify(str(error), type="negative", position="top")
                            return
                        finally:
                            db_split.close()

                        ui.navigate.to(target)

                    ui.button(
                        "Start split bill",
                        icon="groups",
                        on_click=start_split,
                    ).classes("pruvio-primary w-full mt-4 py-3")

        bottom_nav("history")
