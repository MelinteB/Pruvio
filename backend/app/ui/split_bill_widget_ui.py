from nicegui import ui

from app.db.database import SessionLocal
from app.models.receipt_item import ReceiptItem


def get_case_items(case_id: int) -> list[ReceiptItem]:
    db = SessionLocal()

    try:
        return (
            db.query(ReceiptItem)
            .filter(ReceiptItem.case_id == case_id)
            .order_by(ReceiptItem.id.asc())
            .all()
        )
    finally:
        db.close()


def save_split_bill_selection(
    case_id: int,
    selected_item_ids: list[int],
    tip_percent: float,
    service_charge: float
) -> dict:
    db = SessionLocal()

    try:
        items = (
            db.query(ReceiptItem)
            .filter(ReceiptItem.case_id == case_id)
            .order_by(ReceiptItem.id.asc())
            .all()
        )

        selected_set = set(selected_item_ids)
        selected_items = []

        for item in items:
            item.selected_by_user = item.id in selected_set

            if item.selected_by_user:
                selected_items.append(item)

        subtotal = round(
            sum(item.total_price for item in selected_items),
            2
        )

        tip_amount = round(
            subtotal * tip_percent / 100,
            2
        )

        total_to_pay = round(
            subtotal + service_charge + tip_amount,
            2
        )

        currency = selected_items[0].currency if selected_items else "RON"

        db.commit()

        return {
            "case_id": case_id,
            "selected_items_count": len(selected_items),
            "selected_item_ids": [item.id for item in selected_items],
            "subtotal": subtotal,
            "tip_percent": tip_percent,
            "tip_amount": tip_amount,
            "service_charge": service_charge,
            "total_to_pay": total_to_pay,
            "currency": currency,
            "message": (
                f"Total de plata: {total_to_pay:.2f} {currency}. "
                f"Subtotal: {subtotal:.2f} {currency}, "
                f"tips: {tip_amount:.2f} {currency}, "
                f"service: {service_charge:.2f} {currency}."
            )
        }

    finally:
        db.close()


def setup_split_bill_widget_ui():
    @ui.page("/split-bill/cases/{case_id}/widget-ui")
    def split_bill_widget(case_id: int):
        items = get_case_items(case_id)

        ui.page_title("Pruvio Split Bill")

        ui.colors(
            primary="#0f172a",
            secondary="#64748b",
            accent="#0284c7",
            positive="#047857",
            negative="#b91c1c"
        )

        ui.add_head_html(
            """
            <style>
                body {
                    background:
                        radial-gradient(circle at top left, rgba(14,165,233,.14), transparent 34%),
                        linear-gradient(180deg, #ffffff 0%, #f5f7fb 42%, #e2e8f0 100%);
                }

                .pruvio-page {
                    width: 100%;
                    min-height: 100vh;
                    padding: 18px;
                }

                .pruvio-shell {
                    width: 100%;
                    max-width: 1120px;
                    margin: 0 auto;
                }

                .pruvio-card {
                    border-radius: 28px;
                    box-shadow: 0 18px 50px rgba(15, 23, 42, 0.10);
                    border: 1px solid rgba(226, 232, 240, 0.95);
                    background: rgba(255, 255, 255, 0.94);
                    backdrop-filter: blur(12px);
                }

                .pruvio-item-card {
                    border-radius: 20px;
                    border: 1px solid #e2e8f0;
                    background: #ffffff;
                    transition: all .18s ease;
                }

                .pruvio-item-card:hover {
                    background: #f8fafc;
                    border-color: #cbd5e1;
                }

                .pruvio-mobile-bar {
                    display: none;
                }

                @media (max-width: 800px) {
                    .pruvio-page {
                        padding: 12px;
                        padding-bottom: 110px;
                    }

                    .pruvio-desktop-summary {
                        display: none;
                    }

                    .pruvio-mobile-bar {
                        display: block;
                        position: fixed;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        z-index: 1000;
                        padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
                        background: rgba(255, 255, 255, 0.96);
                        border-top: 1px solid #e2e8f0;
                        box-shadow: 0 -12px 35px rgba(15, 23, 42, 0.12);
                        backdrop-filter: blur(14px);
                    }
                }
            </style>
            """
        )

        selected_item_ids: set[int] = set()
        checkbox_by_item_id = {}

        item_data = [
            {
                "id": item.id,
                "name": item.name,
                "quantity": float(item.quantity or 1),
                "unit_price": float(item.unit_price or 0),
                "total_price": float(item.total_price or 0),
                "currency": item.currency or "RON",
            }
            for item in items
        ]

        currency = item_data[0]["currency"] if item_data else "RON"
        receipt_total = round(
            sum(item["total_price"] for item in item_data),
            2
        )

        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):

                with ui.row().classes(
                    "w-full items-center justify-between gap-3"
                ):
                    with ui.row().classes("items-center gap-3"):
                        ui.label("P").classes(
                            "w-11 h-11 rounded-2xl bg-slate-900 text-white "
                            "font-black text-xl flex items-center justify-center shadow-lg"
                        )

                        with ui.column().classes("gap-0"):
                            ui.label("Pruvio").classes(
                                "text-lg font-black text-slate-900 leading-tight"
                            )
                            ui.label("Smart split bill assistant").classes(
                                "text-xs text-slate-500"
                            )

                    ui.label(f"Case #{case_id}").classes(
                        "hidden sm:block px-3 py-2 rounded-full bg-white "
                        "border border-slate-200 text-xs text-slate-500 shadow-sm"
                    )

                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    with ui.row().classes(
                        "w-full items-start justify-between gap-5 flex-col sm:flex-row"
                    ):
                        with ui.column().classes("gap-2"):
                            ui.label("Selecteaza ce vrei sa platesti").classes(
                                "text-3xl sm:text-5xl font-black text-slate-900 "
                                "tracking-tight leading-tight"
                            )

                            ui.label(
                                "Alege produsele tale, adauga tips daca doresti "
                                "si confirma calculul."
                            ).classes(
                                "text-sm sm:text-base text-slate-500 leading-relaxed"
                            )

                        with ui.column().classes(
                            "bg-slate-100 border border-slate-200 rounded-2xl "
                            "px-4 py-3 min-w-[160px]"
                        ):
                            ui.label("Total bon").classes(
                                "text-xs text-slate-500"
                            )
                            ui.label(f"{receipt_total:.2f} {currency}").classes(
                                "text-2xl font-black text-slate-900"
                            )

                if not item_data:
                    with ui.card().classes("pruvio-card w-full p-6"):
                        ui.label("Nu am gasit produse pentru acest bon.").classes(
                            "text-slate-600"
                        )
                    return

                with ui.row().classes(
                    "w-full gap-4 items-start flex-col lg:flex-row"
                ):

                    with ui.card().classes(
                        "pruvio-card w-full lg:flex-1 p-0 overflow-hidden"
                    ):
                        with ui.column().classes("w-full gap-0"):

                            with ui.row().classes(
                                "w-full items-center justify-between p-5 "
                                "border-b border-slate-200"
                            ):
                                with ui.column().classes("gap-1"):
                                    ui.label("Produse extrase").classes(
                                        "text-lg font-black text-slate-900"
                                    )

                                    selected_count_label = ui.label(
                                        "0 produse selectate"
                                    ).classes("text-sm text-slate-500")

                                with ui.row().classes("gap-2"):
                                    select_all_button = ui.button(
                                        "Selecteaza tot"
                                    ).props("outline").classes(
                                        "rounded-full text-xs"
                                    )

                                    clear_button = ui.button(
                                        "Sterge"
                                    ).props("outline").classes(
                                        "rounded-full text-xs"
                                    )

                            items_container = ui.column().classes(
                                "w-full gap-2 p-3"
                            )

                    with ui.card().classes(
                        "pruvio-card pruvio-desktop-summary "
                        "w-full lg:w-[370px] p-5 sticky top-4"
                    ):
                        ui.label("Rezumat plata").classes(
                            "text-lg font-black text-slate-900"
                        )

                        with ui.card().classes(
                            "w-full bg-slate-100 border border-slate-200 "
                            "rounded-2xl shadow-none p-4 mt-3"
                        ):
                            with ui.row().classes("w-full justify-between"):
                                ui.label("Produse").classes("text-slate-500")
                                summary_count = ui.label("0").classes("font-bold")

                            with ui.row().classes("w-full justify-between mt-2"):
                                ui.label("Subtotal").classes("text-slate-500")
                                subtotal_label = ui.label(
                                    f"0.00 {currency}"
                                ).classes("font-bold")

                            with ui.row().classes("w-full justify-between mt-2"):
                                ui.label("Tips").classes("text-slate-500")
                                tips_label = ui.label(
                                    f"0.00 {currency}"
                                ).classes("font-bold")

                            with ui.row().classes("w-full justify-between mt-2"):
                                ui.label("Service").classes("text-slate-500")
                                service_label = ui.label(
                                    f"0.00 {currency}"
                                ).classes("font-bold")

                            ui.separator().classes("my-3")

                            ui.label("Total de plata").classes(
                                "text-xs text-slate-500"
                            )

                            total_label = ui.label(
                                f"0.00 {currency}"
                            ).classes(
                                "text-4xl font-black text-slate-900 tracking-tight"
                            )

                        ui.label("Tips rapid").classes(
                            "text-sm font-bold text-slate-600 mt-4"
                        )

                        with ui.row().classes("w-full gap-2"):
                            tip_buttons = {}

                            for value in [0, 5, 10, 15]:
                                tip_buttons[value] = ui.button(
                                    f"{value}%"
                                ).props("outline").classes(
                                    "rounded-2xl flex-1"
                                )

                        tip_input = ui.number(
                            label="Tips custom %",
                            value=0,
                            min=0,
                            max=100,
                            step=1
                        ).classes("w-full mt-3").props("outlined")

                        service_input = ui.number(
                            label="Service charge",
                            value=0,
                            min=0,
                            step=0.01
                        ).classes("w-full").props("outlined")

                        confirm_button = ui.button(
                            "Confirma selectie"
                        ).classes(
                            "w-full h-13 rounded-2xl bg-slate-900 "
                            "text-white font-black mt-3"
                        )

                        status_label = ui.label("").classes(
                            "text-sm mt-3 text-slate-500"
                        )

                        ui.label(
                            "Pruvio salveaza doar selectia pentru calcul. "
                            "Nu se initiaza plata automat."
                        ).classes(
                            "text-xs text-slate-400 text-center mt-3 leading-relaxed"
                        )

            with ui.element("div").classes("pruvio-mobile-bar"):
                with ui.row().classes(
                    "w-full max-w-[560px] mx-auto items-center justify-between gap-3"
                ):
                    with ui.column().classes("gap-0"):
                        mobile_count_label = ui.label(
                            "0 produse"
                        ).classes("text-xs text-slate-500 font-bold")

                        mobile_total_label = ui.label(
                            f"0.00 {currency}"
                        ).classes(
                            "text-2xl font-black text-slate-900 tracking-tight"
                        )

                    mobile_confirm_button = ui.button(
                        "Confirma"
                    ).classes(
                        "h-12 rounded-2xl bg-slate-900 text-white font-black px-5"
                    )

        def calculate_local():
            selected_items = [
                item
                for item in item_data
                if item["id"] in selected_item_ids
            ]

            subtotal = round(
                sum(item["total_price"] for item in selected_items),
                2
            )

            tip_percent = float(tip_input.value or 0)
            service_charge = float(service_input.value or 0)

            tip_percent = max(0, min(tip_percent, 100))
            service_charge = max(0, service_charge)

            tip_amount = round(
                subtotal * tip_percent / 100,
                2
            )

            total_to_pay = round(
                subtotal + service_charge + tip_amount,
                2
            )

            selected_count_label.set_text(
                f"{len(selected_items)} produse selectate"
            )

            summary_count.set_text(str(len(selected_items)))
            subtotal_label.set_text(f"{subtotal:.2f} {currency}")
            tips_label.set_text(f"{tip_amount:.2f} {currency}")
            service_label.set_text(f"{service_charge:.2f} {currency}")
            total_label.set_text(f"{total_to_pay:.2f} {currency}")

            mobile_count_label.set_text(
                f"{len(selected_items)} produse"
            )
            mobile_total_label.set_text(
                f"{total_to_pay:.2f} {currency}"
            )

            if selected_items:
                confirm_button.enable()
                mobile_confirm_button.enable()
            else:
                confirm_button.disable()
                mobile_confirm_button.disable()

        def on_checkbox_change(item_id: int, checked: bool):
            if checked:
                selected_item_ids.add(item_id)
            else:
                selected_item_ids.discard(item_id)

            calculate_local()

        def select_all():
            selected_item_ids.clear()

            for item in item_data:
                selected_item_ids.add(item["id"])
                checkbox_by_item_id[item["id"]].set_value(True)

            calculate_local()

        def clear_selection():
            selected_item_ids.clear()

            for checkbox in checkbox_by_item_id.values():
                checkbox.set_value(False)

            calculate_local()

        def set_tip(value: int):
            tip_input.set_value(value)

            for tip_value, button in tip_buttons.items():
                if tip_value == value:
                    button.props("unelevated")
                    button.classes(
                        "bg-slate-900 text-white",
                        remove="text-slate-900"
                    )
                else:
                    button.props("outline")
                    button.classes(
                        "text-slate-900",
                        remove="bg-slate-900 text-white"
                    )

            calculate_local()

        def submit_selection():
            if not selected_item_ids:
                status_label.set_text("Selecteaza cel putin un produs.")
                status_label.classes(
                    "text-red-700",
                    remove="text-green-700 text-slate-500"
                )
                ui.notify(
                    "Selecteaza cel putin un produs.",
                    type="warning",
                    position="top"
                )
                return

            result = save_split_bill_selection(
                case_id=case_id,
                selected_item_ids=list(selected_item_ids),
                tip_percent=float(tip_input.value or 0),
                service_charge=float(service_input.value or 0)
            )

            status_label.set_text(result["message"])
            status_label.classes(
                "text-green-700",
                remove="text-red-700 text-slate-500"
            )

            ui.notify(
                "Selectia a fost salvata.",
                type="positive",
                position="top"
            )

        with items_container:
            for item in item_data:
                with ui.card().classes(
                    "pruvio-item-card w-full shadow-none p-4"
                ):
                    with ui.row().classes(
                        "w-full items-center justify-between gap-3"
                    ):
                        with ui.row().classes("items-center gap-3 flex-1"):
                            checkbox = ui.checkbox(
                                value=False,
                                on_change=lambda e, item_id=item["id"]: on_checkbox_change(
                                    item_id=item_id,
                                    checked=e.value
                                )
                            )

                            checkbox_by_item_id[item["id"]] = checkbox

                            with ui.column().classes("gap-1 flex-1"):
                                ui.label(item["name"]).classes(
                                    "font-black text-slate-900 leading-tight"
                                )

                                ui.label(
                                    f"Qty {item['quantity']:g} · "
                                    f"Unit {item['unit_price']:.2f} {currency}"
                                ).classes(
                                    "text-xs text-slate-500"
                                )

                        ui.label(
                            f"{item['total_price']:.2f} {currency}"
                        ).classes(
                            "font-black text-slate-900 whitespace-nowrap"
                        )

        select_all_button.on("click", select_all)
        clear_button.on("click", clear_selection)

        for value, button in tip_buttons.items():
            button.on(
                "click",
                lambda _, value=value: set_tip(value)
            )

        tip_input.on(
            "update:model-value",
            lambda _: calculate_local()
        )

        service_input.on(
            "update:model-value",
            lambda _: calculate_local()
        )

        confirm_button.on("click", submit_selection)
        mobile_confirm_button.on("click", submit_selection)

        confirm_button.disable()
        mobile_confirm_button.disable()

        set_tip(0)
        calculate_local()