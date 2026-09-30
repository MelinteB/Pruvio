import hashlib
import json

from fastapi import Request
from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.split_bill_session_service import (
    close_split_bill_session,
    get_split_bill_participant_by_token,
    get_split_bill_session_by_token,
    get_split_bill_session_summary,
    join_split_bill_session,
    save_participant_selection,
    update_expected_participants_count,
)
from app.ui.app_shell import app_header, display_item_name, is_integer_quantity, quantity_text, setup_page_head
from app.ui.auth_state import require_login

EPS = 1e-6


def _error_page(title: str, message: str) -> None:
    setup_page_head(f"{title} · Pruvio")
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Split bill")
            with ui.card().classes("pruvio-card w-full p-6"):
                ui.label(title).classes("text-xl font-black text-slate-950")
                ui.label(message).classes("text-sm text-slate-500")
                ui.button("Go home", on_click=lambda: ui.navigate.to("/")).classes("pruvio-primary mt-3")


def _share_link(url: str, text: str) -> None:
    script = f"""
    (async () => {{
      const data = {{title: 'Pruvio split bill', text: {json.dumps(text)}, url: {json.dumps(url)}}};
      if (navigator.share) {{ try {{ await navigator.share(data); return; }} catch (e) {{}} }}
      await navigator.clipboard.writeText(data.text + '\\n' + data.url);
    }})();
    """
    ui.run_javascript(script)


def _copy_link(url: str, lang: str) -> None:
    ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(url)})")
    ui.notify("Link copiat." if lang == "ro" else "Link copied.", type="positive", position="top")


def _assignment_quantity_for_participant(item: dict, participant_id: int) -> float:
    return round(sum(float(row.get("quantity") or 0) for row in item.get("assignments", []) if row.get("participant_id") == participant_id), 3)


def _other_assignment_quantity(item: dict, participant_id: int) -> float:
    return round(sum(float(row.get("quantity") or 0) for row in item.get("assignments", []) if row.get("participant_id") != participant_id), 3)


def _selection_amount(item: dict, quantity: float) -> float:
    total_quantity = float(item.get("quantity") or 1)
    total_price = float(item.get("total_price") or 0)
    unit_price = float(item.get("unit_price") or (total_price / total_quantity if total_quantity else total_price))
    if abs(quantity - total_quantity) <= EPS:
        return total_price
    return round(unit_price * quantity, 2)


def _summary_digest(summary: dict) -> str:
    payload = {
        "status": summary.get("status"),
        "expected": summary.get("expected_participants_count"),
        "participants": [(p.get("participant_id"), p.get("display_name"), p.get("total"), p.get("items_count")) for p in summary.get("participants", [])],
        "items": [
            (item.get("item_id"), [(a.get("participant_id"), a.get("quantity"), a.get("amount")) for a in item.get("assignments", [])])
            for item in summary.get("items", [])
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def setup_split_bill_session_widget_ui() -> None:
    @ui.page("/split-bill/sessions/{token}/join")
    def split_bill_join_page(token: str):
        _render_join_page(token)

    @ui.page("/split-bill/sessions/{token}/widget-ui")
    def split_bill_owner_page(token: str, request: Request):
        raw = request.query_params.get("participant_id")
        try:
            participant_id = int(raw) if raw else None
        except ValueError:
            participant_id = None
        if participant_id is None:
            ui.navigate.to(f"/split-bill/sessions/{token}/join")
            return
        return_to = f"/split-bill/sessions/{token}/widget-ui?participant_id={participant_id}"
        user_id = require_login(return_to)
        if user_id is None:
            return
        db = SessionLocal()
        try:
            session = get_split_bill_session_by_token(db, token)
            if not session or session.owner_user_id != user_id:
                _error_page("Owner access required", "Sign in with the account that created this bill.")
                return
        finally:
            db.close()
        _render_split_page(token=token, participant_id=participant_id)

    @ui.page("/split-bill/sessions/{token}/p/{participant_token}/widget-ui")
    def split_bill_participant_page(token: str, participant_token: str):
        db = SessionLocal()
        try:
            session = get_split_bill_session_by_token(db, token)
            participant = get_split_bill_participant_by_token(db, participant_token)
            if not session or not participant or participant.session_id != session.id:
                _error_page("Invalid link", "This participant link is invalid or expired.")
                return
            participant_id = participant.id
        finally:
            db.close()
        _render_split_page(token=token, participant_id=participant_id)


def _render_join_page(token: str) -> None:
    db = SessionLocal()
    try:
        session = get_split_bill_session_by_token(db, token)
        if not session:
            _error_page("Split bill not found", "The shared link is invalid or expired.")
            return
        summary = get_split_bill_session_summary(db, session)
    finally:
        db.close()
    lang = summary.get("language") or "en"
    setup_page_head(f"{t('Join split bill', lang)} · Pruvio")

    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Join split bill", language=lang)
            with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                ui.label(t("Join this bill", lang)).classes("text-3xl font-black text-slate-950")
                ui.label(
                    "Nu este necesar un cont. Introdu numele și alege ce ai consumat."
                    if lang == "ro" else "No account is needed. Enter your name and choose what you consumed."
                ).classes("text-sm text-slate-500 max-w-2xl")
                with ui.row().classes("gap-2 flex-wrap mt-2"):
                    ui.label(f"{summary['bill_total']:.2f} {summary['currency']}").classes("metric-pill")
                    ui.label(f"{summary['joined_participants_count']}/{summary['expected_participants_count']} {'persoane' if lang == 'ro' else 'people'}").classes("metric-pill")
                    ui.label(f"{summary['remaining_total']:.2f} {summary['currency']} {'rămas' if lang == 'ro' else 'remaining'}").classes("metric-pill metric-accent")
                name_input = ui.input(label=t("Your name", lang)).props("outlined autofocus").classes("w-full mt-4")
                status = ui.label("").classes("text-sm text-slate-500")

                def join():
                    name = (name_input.value or "").strip()
                    if not name:
                        ui.notify("Introdu numele." if lang == "ro" else "Enter your name.", type="warning", position="top")
                        return
                    db_join = SessionLocal()
                    try:
                        current_session = get_split_bill_session_by_token(db_join, token)
                        result = join_split_bill_session(db=db_join, session=current_session, display_name=name, phone_number=None)
                    except Exception as error:
                        ui.notify(str(error), type="negative", position="top")
                        return
                    finally:
                        db_join.close()
                    status.set_text(result.get("message") or "")
                    if result.get("widget_url"):
                        ui.navigate.to(result["widget_url"])
                    else:
                        ui.notify(result.get("message") or "Could not join.", type="warning", position="top")

                ui.button(t("Join bill", lang), icon="arrow_forward", on_click=join).classes("pruvio-primary w-full py-3 mt-2")


def _render_split_page(token: str, participant_id: int) -> None:
    db = SessionLocal()
    try:
        session = get_split_bill_session_by_token(db, token)
        if not session:
            _error_page("Split bill not found", "This session no longer exists.")
            return
        summary = get_split_bill_session_summary(db, session)
    finally:
        db.close()

    current = next((row for row in summary["participants"] if row["participant_id"] == participant_id), None)
    if not current:
        _error_page("Participant not found", "This participant no longer belongs to the bill.")
        return

    lang = summary.get("language") or "en"
    setup_page_head(f"{t('Split bill', lang)} · Pruvio")
    is_owner = current["role"] == "owner"
    currency = summary["currency"]
    dirty = {"value": False}
    initial_digest = {"value": _summary_digest(summary)}
    selected_quantities: dict[int, float] = {
        item["item_id"]: _assignment_quantity_for_participant(item, participant_id)
        for item in summary["items"]
    }

    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Split bill", language=lang)

            with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                with ui.row().classes("w-full items-start justify-between gap-4 flex-col md:flex-row"):
                    with ui.column().classes("gap-1"):
                        ui.label((f"Salut, {current['display_name']}" if lang == "ro" else f"Hi, {current['display_name']}")).classes("text-2xl sm:text-3xl font-black text-slate-950")
                        ui.label(
                            "Alege cantitățile tale. Produsele salvate de ceilalți sunt blocate și marcate cu numele lor."
                            if lang == "ro" else "Choose your quantities. Items saved by others are locked and marked with their names."
                        ).classes("text-sm text-slate-500")
                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.label(f"{summary['bill_total']:.2f} {currency}").classes("metric-pill")
                        ui.label(f"{summary['remaining_total']:.2f} {currency} {'rămas' if lang == 'ro' else 'remaining'}").classes("metric-pill metric-accent")
                        ui.label(f"{summary['joined_participants_count']}/{summary['expected_participants_count']} {'persoane' if lang == 'ro' else 'people'}").classes("metric-pill")

            if is_owner and summary["status"] == "open":
                with ui.card().classes("pruvio-card w-full p-5"):
                    ui.label(t("Invite people", lang)).classes("text-lg font-black text-slate-950")
                    ui.label("Distribuie linkul unic al sesiunii." if lang == "ro" else "Share the session link. Participants only enter their name.").classes("text-xs text-slate-500")
                    with ui.row().classes("w-full gap-2 items-end flex-wrap mt-2"):
                        people_input = ui.number(label=t("People", lang), value=summary["expected_participants_count"], min=summary["joined_participants_count"], max=20, step=1).props("outlined dense").classes("w-28")

                        def update_people():
                            db_count = SessionLocal()
                            try:
                                s = get_split_bill_session_by_token(db_count, token)
                                update_expected_participants_count(db=db_count, session=s, owner_user_id=current["user_id"], expected_participants_count=int(people_input.value or 1))
                            except Exception as error:
                                ui.notify(str(error), type="negative", position="top")
                                return
                            finally:
                                db_count.close()
                            ui.run_javascript("window.location.reload()")

                        ui.button(t("Save", lang), on_click=update_people).classes("pruvio-secondary")
                        ui.button(t("Share", lang), icon="ios_share", on_click=lambda: _share_link(summary["share_url"], "Alătură-te notei mele Pruvio" if lang == "ro" else "Join my Pruvio split bill")).classes("pruvio-primary")
                        ui.button(icon="content_copy", on_click=lambda: _copy_link(summary["share_url"], lang)).props("flat round")

            with ui.card().classes("pruvio-card w-full p-0 overflow-hidden"):
                with ui.row().classes("w-full items-center justify-between gap-3 px-5 py-4 border-b border-slate-100"):
                    with ui.column().classes("gap-0"):
                        ui.label(t("Your items", lang)).classes("text-lg font-black text-slate-950")
                        ui.label("Modificările salvate de ceilalți apar automat în câteva secunde." if lang == "ro" else "Saved changes from other participants appear automatically within a few seconds.").classes("text-xs text-slate-500")
                    my_total_label = ui.label("").classes("text-sm font-black text-emerald-700")

                quantity_labels = {}
                minus_buttons = {}
                plus_buttons = {}

                def max_for_me(item: dict) -> float:
                    total = float(item.get("quantity") or 1)
                    other = _other_assignment_quantity(item, participant_id)
                    return max(0.0, total - other)

                def refresh_selection_ui():
                    amount = units = 0.0
                    lines = 0
                    for item in summary["items"]:
                        item_id = item["item_id"]
                        qty = max(0.0, float(selected_quantities.get(item_id, 0)))
                        if qty > EPS:
                            lines += 1
                            units += qty if is_integer_quantity(float(item["quantity"])) else 1
                            amount += _selection_amount(item, qty)
                        if item_id in quantity_labels:
                            quantity_labels[item_id].set_text(quantity_text(qty))
                        if item_id in minus_buttons:
                            (minus_buttons[item_id].enable() if qty > EPS and summary["status"] == "open" else minus_buttons[item_id].disable())
                        if item_id in plus_buttons:
                            (plus_buttons[item_id].enable() if qty + 1 <= max_for_me(item) + EPS and summary["status"] == "open" else plus_buttons[item_id].disable())
                    my_total_label.set_text(f"{lines} {'linii' if lang == 'ro' else 'lines'} · {quantity_text(units)} {'unități' if lang == 'ro' else 'units'} · {amount:.2f} {currency}")

                def change_discrete(item: dict, delta: int):
                    dirty["value"] = True
                    item_id = item["item_id"]
                    current_qty = float(selected_quantities.get(item_id, 0))
                    selected_quantities[item_id] = max(0.0, min(max_for_me(item), current_qty + delta))
                    refresh_selection_ui()

                def toggle_atomic(item: dict, checked: bool):
                    dirty["value"] = True
                    selected_quantities[item["item_id"]] = max_for_me(item) if checked else 0.0
                    refresh_selection_ui()

                with ui.column().classes("w-full gap-0"):
                    for item in summary["items"]:
                        item_id = item["item_id"]
                        total_qty = float(item.get("quantity") or 1)
                        unit_price = float(item.get("unit_price") or 0)
                        mine = selected_quantities[item_id]
                        other_qty = _other_assignment_quantity(item, participant_id)
                        discrete_multi = is_integer_quantity(total_qty) and total_qty > 1
                        fully_taken_by_other = other_qty >= total_qty - EPS and mine <= EPS
                        atomic_locked = (not discrete_multi) and other_qty > EPS and mine <= EPS
                        other_assignments = [a for a in item.get("assignments", []) if a.get("participant_id") != participant_id]

                        row_classes = "item-row w-full items-center gap-3 px-4 sm:px-5 py-4"
                        if fully_taken_by_other:
                            row_classes += " bg-slate-100 opacity-70"
                        with ui.row().classes(row_classes):
                            if fully_taken_by_other:
                                ui.icon("block").classes("text-slate-400 shrink-0")
                            elif discrete_multi:
                                with ui.row().classes("items-center gap-1 shrink-0"):
                                    minus = ui.button(icon="remove", on_click=lambda item=item: change_discrete(item, -1)).props("flat round dense").classes("text-slate-700")
                                    qty_label = ui.label(quantity_text(mine)).classes("w-7 text-center font-black text-slate-950")
                                    plus = ui.button(icon="add", on_click=lambda item=item: change_discrete(item, 1)).props("flat round dense").classes("text-slate-700")
                                    minus_buttons[item_id] = minus
                                    plus_buttons[item_id] = plus
                                    quantity_labels[item_id] = qty_label
                            else:
                                checkbox = ui.checkbox(value=mine > EPS, on_change=lambda e, item=item: toggle_atomic(item, bool(e.value))).props("dense")
                                if atomic_locked or summary["status"] != "open":
                                    checkbox.disable()

                            with ui.column().classes("gap-1 flex-1 min-w-0"):
                                name_classes = "text-sm sm:text-base font-bold leading-snug"
                                if fully_taken_by_other:
                                    name_classes += " text-slate-400 line-through"
                                else:
                                    name_classes += " text-slate-950"
                                ui.label(display_item_name(item)).classes(name_classes)
                                if discrete_multi:
                                    detail = f"{quantity_text(total_qty)} {'pe bon' if lang == 'ro' else 'on receipt'} · {unit_price:.2f} {currency} {'fiecare' if lang == 'ro' else 'each'}"
                                else:
                                    detail = f"{quantity_text(total_qty)} {'unitate' if lang == 'ro' else 'unit'} · {unit_price:.2f} {currency}"
                                ui.label(detail).classes("text-xs text-slate-500")
                                if other_assignments:
                                    with ui.row().classes("gap-1 flex-wrap mt-1"):
                                        for assignment in other_assignments:
                                            q = float(assignment.get("quantity") or 0)
                                            mark = f"✓ {assignment.get('assigned_to')}"
                                            if discrete_multi:
                                                mark += f" ×{quantity_text(q)}"
                                            ui.label(mark).classes("text-[11px] font-bold bg-slate-200 text-slate-600 px-2 py-1 rounded-full")

                            ui.label(f"{float(item['total_price']):.2f} {currency}").classes("text-sm font-black text-slate-950 whitespace-nowrap")

                def save_selection():
                    db_save = SessionLocal()
                    try:
                        s = get_split_bill_session_by_token(db_save, token)
                        save_participant_selection(db=db_save, session=s, participant_id=participant_id, selected_quantities=selected_quantities)
                    except Exception as error:
                        ui.notify(str(error), type="negative", position="top")
                        return
                    finally:
                        db_save.close()
                    dirty["value"] = False
                    ui.notify(t("Your selection was saved.", lang), type="positive", position="top")
                    ui.run_javascript("window.location.reload()")

                with ui.row().classes("w-full gap-2 p-4 border-t border-slate-100 flex-wrap"):
                    save_button = ui.button(t("Save my selection", lang), icon="check", on_click=save_selection).classes("pruvio-primary flex-1 min-w-[190px] py-3")
                    if summary["status"] != "open":
                        save_button.disable()
                    ui.button(t("Refresh", lang), icon="refresh", on_click=lambda: ui.run_javascript("window.location.reload()")).classes("pruvio-secondary")
                refresh_selection_ui()

            with ui.card().classes("pruvio-card w-full p-5"):
                ui.label(t("Participants", lang)).classes("text-lg font-black text-slate-950")
                with ui.column().classes("w-full gap-0 mt-1"):
                    for participant in summary["participants"]:
                        role = t("Owner", lang) if participant["role"] == "owner" else t("Participant", lang)
                        with ui.row().classes("item-row w-full items-center justify-between gap-3 py-3"):
                            with ui.column().classes("gap-0"):
                                ui.label(participant["display_name"]).classes("font-bold text-slate-900")
                                ui.label(f"{role} · {participant['items_count']} {'linii' if lang == 'ro' else 'lines'}").classes("text-xs text-slate-400")
                            ui.label(f"{participant['total']:.2f} {currency}").classes("font-black text-slate-950")

            if is_owner and summary["status"] == "open":
                with ui.card().classes("pruvio-card w-full p-5"):
                    ui.label(t("Finish split", lang)).classes("text-lg font-black text-slate-950")
                    ui.label(summary["close_block_reason"] or ("Totul este alocat." if lang == "ro" else "Everything is assigned.")).classes("text-xs text-slate-500")

                    def close_bill():
                        db_close = SessionLocal()
                        try:
                            s = get_split_bill_session_by_token(db_close, token)
                            close_split_bill_session(db=db_close, session=s, owner_user_id=current["user_id"])
                        except Exception as error:
                            ui.notify(str(error), type="negative", position="top")
                            return
                        finally:
                            db_close.close()
                        ui.navigate.to(f"/receipt/{summary['case_id']}")

                    close_button = ui.button(t("Close split", lang), icon="done_all", on_click=close_bill).classes("pruvio-primary mt-3")
                    if not summary["can_close"]:
                        close_button.disable()

            # Near-real-time synchronization across every active session link.
            # We avoid reloading while this participant has unsaved local changes.
            def poll_updates():
                if dirty["value"]:
                    return
                db_poll = SessionLocal()
                try:
                    s = get_split_bill_session_by_token(db_poll, token)
                    if not s:
                        return
                    latest = get_split_bill_session_summary(db_poll, s)
                finally:
                    db_poll.close()
                digest = _summary_digest(latest)
                if digest != initial_digest["value"]:
                    initial_digest["value"] = digest
                    ui.run_javascript("window.location.reload()")

            ui.timer(2.0, poll_updates)
