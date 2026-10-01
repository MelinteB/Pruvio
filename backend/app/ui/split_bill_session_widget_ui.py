import hashlib
import json
import urllib.parse

from fastapi import Request
from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.split_bill_session_service import (
    close_split_bill_session,
    get_owner_participant,
    get_participant_by_session_and_user,
    get_split_bill_participant_by_token,
    get_split_bill_session_by_token,
    get_split_bill_session_summary,
    join_split_bill_session_as_user,
    record_participant_payment_status,
    save_participant_selection,
    send_participant_reminder,
    update_expected_participants_count,
    update_session_tip,
)
from app.ui.app_shell import app_header, display_item_name, is_integer_quantity, quantity_text, setup_page_head
from app.ui.auth_state import get_logged_in_user, require_login, logout_user, get_ui_language, POST_LOGIN_PATH_KEY
from nicegui import app as nicegui_app

EPS = 1e-6


def _error_page(title: str, message: str) -> None:
    setup_page_head(f"{title} · Pruvs")
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Split bill")
            with ui.card().classes("pruvio-card w-full p-6"):
                ui.label(title).classes("text-xl font-black text-slate-950")
                ui.label(message).classes("text-sm text-slate-500")
                ui.button("Go home", on_click=lambda: ui.navigate.to("/")).classes("pruvio-primary mt-3 px-4")


def _owner_shared_link_page(token: str, language: str) -> None:
    ro = language == "ro"
    setup_page_head("Pruvs · " + ("Ești proprietarul acestei note" if ro else "You own this bill"))
    with ui.element("main").classes("pruvio-page"), ui.column().classes("pruvio-shell gap-4"):
        app_header("Split bill", language=language)
        with ui.card().classes("pruvio-card w-full max-w-xl mx-auto p-6 sm:p-8 gap-4"):
            ui.icon("person_outline", size="40px").classes("text-blue-600")
            ui.label("Ești proprietarul acestei note" if ro else "You are the owner of this bill").classes("text-2xl font-black text-slate-950")
            ui.label("Nu te poți conecta prin linkul partajat. Acest link este destinat altor utilizatori. Deconectează-te sau folosește alt cont." if ro else
                     "You are the owner of this bill and cannot join through the shared link. This link is for other users. Sign out or use another account.").classes("text-sm text-slate-500 leading-relaxed").props("role=alert")

            def sign_out():
                logout_user()
                ui.navigate.to("/")

            def switch_account():
                logout_user()
                nicegui_app.storage.user[POST_LOGIN_PATH_KEY] = f"/split-bill/sessions/{token}/join"
                ui.navigate.to("/")

            ui.button("Folosește alt cont" if ro else "Use another account", icon="switch_account", on_click=switch_account).classes("pruvio-primary w-full py-3")
            ui.button("Deconectare" if ro else "Sign out", icon="logout", on_click=sign_out).classes("pruvio-secondary w-full py-3")


def _share_link(url: str, text: str) -> None:
    ui.run_javascript(f"""return await (async()=>{{const d={{title:'Pruvs split bill',text:{json.dumps(text)},url:{json.dumps(url)}}};if(navigator.share){{try{{await navigator.share(d);return true}}catch(e){{}}}}await navigator.clipboard.writeText(d.text+'\\n'+d.url);return true;}})();""")


def _assignment_quantity_for_participant(item: dict, participant_id: int) -> float:
    return round(sum(float(r.get("quantity") or 0) for r in item.get("assignments", []) if r.get("participant_id") == participant_id), 3)


def _other_assignment_quantity(item: dict, participant_id: int) -> float:
    return round(sum(float(r.get("quantity") or 0) for r in item.get("assignments", []) if r.get("participant_id") != participant_id), 3)


def _selection_amount(item: dict, quantity: float) -> float:
    total_quantity = float(item.get("quantity") or 1)
    total_price = float(item.get("total_price") or 0)
    unit_price = float(item.get("unit_price") or (total_price / total_quantity if total_quantity else total_price))
    return total_price if abs(quantity-total_quantity) <= EPS else round(unit_price*quantity, 2)


def _summary_digest(summary: dict) -> str:
    payload = {
        "status": summary.get("status"), "expected": summary.get("expected_participants_count"),
        "tip": (summary.get("tip_mode"), summary.get("tip_value"), summary.get("tip_total")),
        "participants": [(p.get("participant_id"),p.get("total"),p.get("payment_status"),p.get("payment_method"),p.get("reminder_at")) for p in summary.get("participants",[])],
        "items": [(i.get("item_id"),[(a.get("participant_id"),a.get("quantity"),a.get("amount")) for a in i.get("assignments",[])]) for i in summary.get("items",[])],
        "owner_payment_details": summary.get("owner_payment_details"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def setup_split_bill_session_widget_ui() -> None:
    @ui.page("/split-bill/sessions/{token}/join")
    def split_bill_join_page(token: str):
        _render_join_page(token)

    @ui.page("/split-bill/sessions/{token}/widget-ui")
    def split_bill_owner_page(token: str, request: Request):
        raw = request.query_params.get("participant_id")
        try: participant_id = int(raw) if raw else None
        except ValueError: participant_id = None
        if participant_id is None:
            ui.navigate.to(f"/split-bill/sessions/{token}/join"); return
        return_to = f"/split-bill/sessions/{token}/widget-ui?participant_id={participant_id}"
        user_id = require_login(return_to)
        if user_id is None: return
        db = SessionLocal()
        try:
            session = get_split_bill_session_by_token(db, token)
            participant = get_owner_participant(db, session) if session else None
            if not session or session.owner_user_id != user_id or not participant or participant.id != participant_id:
                _error_page("Owner access required", "Sign in with the account that created this bill."); return
        finally: db.close()
        _render_split_page(token, participant_id, user_id)

    @ui.page("/split-bill/sessions/{token}/p/{participant_token}/widget-ui")
    def split_bill_participant_page(token: str, participant_token: str):
        return_to = f"/split-bill/sessions/{token}/p/{participant_token}/widget-ui"
        user_id = require_login(return_to)
        if user_id is None: return
        db = SessionLocal()
        try:
            session = get_split_bill_session_by_token(db, token)
            if session and session.owner_user_id == user_id:
                _owner_shared_link_page(token, get_ui_language()); return
            participant = get_split_bill_participant_by_token(db, participant_token)
            if not session or not participant or participant.session_id != session.id:
                _error_page("Invalid link", "This participant link is invalid or expired."); return
            if participant.user_id != user_id:
                _error_page("Account mismatch", "This participant link belongs to another Pruvs account."); return
            participant_id = participant.id
        finally: db.close()
        _render_split_page(token, participant_id, user_id)


def _render_join_page(token: str) -> None:
    return_to = f"/split-bill/sessions/{token}/join"
    user_id = require_login(return_to)
    if user_id is None: return
    db = SessionLocal()
    try:
        session = get_split_bill_session_by_token(db, token)
        user = get_logged_in_user(db)
        if not session or not user:
            _error_page("Split bill not found", "The shared link is invalid or expired."); return
        if session.owner_user_id == user.id:
            _owner_shared_link_page(token, user.preferred_language or "en"); return
        lang = user.preferred_language or "en"
        existing = get_participant_by_session_and_user(db, session, user)
        summary = get_split_bill_session_summary(db, session)
    finally: db.close()

    setup_page_head(f"{t('Join split bill', lang)} · Pruvs")
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Join split bill", language=lang)
            with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                ui.label(t("Sign in to join this bill", lang)).classes("text-2xl sm:text-3xl font-black text-slate-950")
                ui.label(t("Your account is used so selections and payments stay connected to you.", lang)).classes("text-sm text-slate-500 max-w-2xl")
                with ui.row().classes("gap-2 flex-wrap mt-3"):
                    ui.label(f"{summary['grand_total']:.2f} {summary['currency']}").classes("metric-pill")
                    ui.label(f"{summary['joined_participants_count']}/{summary['expected_participants_count']} {'persoane' if lang=='ro' else 'people'}").classes("metric-pill")
                ui.label((f"Conectat ca {user.name or user.email or user.phone_number}" if lang=='ro' else f"Signed in as {user.name or user.email or user.phone_number}")).classes("text-sm font-semibold text-slate-700 mt-4")

                def join():
                    dbj=SessionLocal()
                    try:
                        ss=get_split_bill_session_by_token(dbj,token); uu=get_logged_in_user(dbj)
                        if ss and uu and ss.owner_user_id == uu.id:
                            ui.navigate.to(f"/split-bill/sessions/{token}/join"); return
                        result=join_split_bill_session_as_user(dbj,ss,uu)
                    except Exception as e:
                        ui.notify(str(e),type="negative"); return
                    finally: dbj.close()
                    ui.navigate.to(result["widget_url"])

                label = "Deschide împărțirea" if existing and lang=='ro' else ("Open split" if existing else t("Join bill", lang))
                ui.button(label, icon="arrow_forward", on_click=join).classes("pruvio-primary self-start px-5 mt-3")


def _render_split_page(token: str, participant_id: int, user_id: int) -> None:
    db=SessionLocal()
    try:
        session=get_split_bill_session_by_token(db,token); summary=get_split_bill_session_summary(db,session) if session else None; user=get_logged_in_user(db)
    finally: db.close()
    if not summary or not user:
        _error_page("Split bill not found","This session no longer exists."); return
    current=next((p for p in summary["participants"] if p["participant_id"]==participant_id),None)
    if not current or current.get("user_id") != user_id:
        _error_page("Participant not found","This participant is not connected to your account."); return

    lang=user.preferred_language or "en"; currency=summary["currency"]; is_owner=current["role"]=="owner"
    setup_page_head(f"{t('Split bill',lang)} · Pruvs")
    dirty={"value":False}; digest={"value":_summary_digest(summary)}
    selected={i["item_id"]:_assignment_quantity_for_participant(i,participant_id) for i in summary["items"]}

    with ui.element("main").classes("pruvio-page"):
      with ui.column().classes("pruvio-shell gap-4"):
        app_header("Split bill",language=lang)
        with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
          with ui.row().classes("w-full justify-between items-start gap-3 flex-wrap"):
            with ui.column().classes("gap-1"):
              ui.label((f"Salut, {current['display_name']}" if lang=='ro' else f"Hi, {current['display_name']}")).classes("text-2xl font-black tracking-tight")
              with ui.row().classes("items-center gap-2"):
                ui.html('<span class="live-dot"></span>',sanitize=False); ui.label(t("Live",lang)).classes("text-xs font-bold text-blue-700")
            if is_owner and summary["status"]=="open":
              ui.button("Share" if lang=='en' else "Distribuie",icon="ios_share",on_click=lambda:_share_link(summary["share_url"],"Pruvs split bill")).classes("pruvio-secondary px-4")
          with ui.row().classes("gap-2 flex-wrap mt-3"):
            ui.label(f"{summary['bill_total']:.2f} {currency} {'bon' if lang=='ro' else 'receipt'}").classes("metric-pill")
            if summary["tip_total"]>0: ui.label(f"+ {summary['tip_total']:.2f} {currency} {t('Tip',lang).lower()}").classes("metric-pill")
            ui.label(f"{summary['grand_total']:.2f} {currency} {'total' if lang=='ro' else 'total'}").classes("metric-pill metric-accent")

          if current.get("reminder_message"):
            with ui.element("div").classes("w-full mt-4 p-3 rounded-xl bg-amber-50 border border-amber-200"):
              ui.label("🔔 " + current["reminder_message"]).classes("text-sm font-semibold text-amber-900")

        if is_owner and summary["status"]=="open":
          with ui.card().classes("pruvio-card w-full p-5"):
            ui.label(t("Tip",lang)).classes("text-lg font-black")
            ui.label("Bacșișul se împarte egal între toți participanții, inclusiv proprietarul." if lang=='ro' else "Tip is divided equally among everyone, including the owner.").classes("text-xs text-slate-500")
            with ui.row().classes("w-full gap-2 items-end flex-wrap mt-3"):
              mode=ui.select({"none":t("No tip",lang),"percent":t("Percent",lang),"fixed":t("Fixed amount",lang)},value=summary["tip_mode"],label=t("Tip",lang)).props("outlined dense").classes("w-44")
              val=ui.number(label=("Valoare" if lang=='ro' else "Value"),value=summary["tip_value"],min=0,step=.5).props("outlined dense").classes("w-36")
              def apply_tip():
                dbt=SessionLocal()
                try: ss=get_split_bill_session_by_token(dbt,token); update_session_tip(dbt,ss,user_id,mode.value,float(val.value or 0))
                except Exception as e: ui.notify(str(e),type="negative"); return
                finally: dbt.close()
                ui.run_javascript("window.location.reload()")
              ui.button(t("Apply tip",lang),icon="percent",on_click=apply_tip).classes("pruvio-secondary px-4")

        with ui.card().classes("pruvio-card w-full overflow-hidden"):
          with ui.column().classes("w-full gap-0"):
            header=ui.row().classes("w-full justify-between items-center px-4 sm:px-5 pt-5 pb-3")
            with header:
              ui.label("Produse" if lang=='ro' else "Items").classes("text-lg font-black")
              my_total=ui.label("").classes("text-sm font-black text-blue-700")

            qlabels={}; pluses={}; minuses={}
            def max_for_me(item): return max(0.0,float(item["quantity"])-_other_assignment_quantity(item,participant_id))
            def refresh_local():
              lines=units=amt=0.0
              for item in summary["items"]:
                iid=item["item_id"]; qty=float(selected.get(iid,0));
                if qty>EPS: lines+=1; units+=qty; amt+=_selection_amount(item,qty)
                if iid in qlabels: qlabels[iid].set_text(quantity_text(qty))
                if iid in minuses:
                  (minuses[iid].enable() if qty>EPS and summary["status"]=="open" else minuses[iid].disable())
                if iid in pluses:
                  (pluses[iid].enable() if qty+1<=max_for_me(item)+EPS and summary["status"]=="open" else pluses[iid].disable())
              tipshare=float(current.get("tip_share") or 0)
              my_total.set_text(f"{amt:.2f} + {tipshare:.2f} {t('Tip',lang).lower()} = {amt+tipshare:.2f} {currency}" if tipshare else f"{amt:.2f} {currency}")
            def discrete(item,delta): dirty["value"]=True; iid=item["item_id"]; selected[iid]=max(0,min(max_for_me(item),float(selected.get(iid,0))+delta)); refresh_local()
            def atomic(item,checked): dirty["value"]=True; selected[item["item_id"]]=max_for_me(item) if checked else 0; refresh_local()

            for item in summary["items"]:
              iid=item["item_id"]; tq=float(item.get("quantity") or 1); mine=float(selected[iid]); other=_other_assignment_quantity(item,participant_id); discrete_multi=is_integer_quantity(tq) and tq>1
              full_other=other>=tq-EPS and mine<=EPS; other_as=[a for a in item.get("assignments",[]) if a.get("participant_id")!=participant_id]
              cls="item-row w-full items-center gap-3 px-4 sm:px-5 py-4" + (" claimed-item" if full_other else "")
              with ui.row().classes(cls):
                if full_other: ui.icon("close").classes("text-slate-400 shrink-0")
                elif discrete_multi:
                  with ui.row().classes("items-center gap-0 shrink-0"):
                    b=ui.button(icon="remove",on_click=lambda item=item:discrete(item,-1)).props("flat round dense").classes("text-slate-500"); minuses[iid]=b
                    l=ui.label(quantity_text(mine)).classes("w-7 text-center font-black"); qlabels[iid]=l
                    b=ui.button(icon="add",on_click=lambda item=item:discrete(item,1)).props("flat round dense").classes("text-slate-500"); pluses[iid]=b
                else:
                  cb=ui.checkbox(value=mine>EPS,on_change=lambda e,item=item:atomic(item,bool(e.value))).props("dense")
                  if (other>EPS and mine<=EPS) or summary["status"]!="open": cb.disable()
                with ui.column().classes("gap-1 flex-1 min-w-0"):
                  ui.label(display_item_name(item)).classes("claim-name text-sm sm:text-base font-bold leading-snug")
                  ui.label(f"{quantity_text(tq)} × {float(item['unit_price']):.2f} {currency}").classes("text-xs text-slate-400")
                  if other_as:
                    with ui.row().classes("gap-1 flex-wrap"):
                      for a in other_as:
                        txt=f"✓ {a.get('assigned_to')}" + (f" ×{quantity_text(float(a.get('quantity') or 0))}" if discrete_multi else "")
                        ui.label(txt).classes("participant-badge")
                ui.label(f"{float(item['total_price']):.2f} {currency}").classes("text-sm font-black whitespace-nowrap")

          def save_sel():
            dbs=SessionLocal()
            try: ss=get_split_bill_session_by_token(dbs,token); save_participant_selection(dbs,ss,participant_id,selected)
            except Exception as e: ui.notify(str(e),type="negative"); return
            finally: dbs.close()
            dirty["value"]=False; ui.notify(t("Your selection was saved.",lang),type="positive"); ui.run_javascript("window.location.reload()")
          with ui.row().classes("w-full justify-end gap-2 p-4 border-t border-slate-100"):
            b=ui.button(t("Save my selection",lang),icon="check",on_click=save_sel).classes("pruvio-primary px-5")
            if summary["status"]!="open": b.disable()
          refresh_local()

        with ui.card().classes("pruvio-card w-full p-5"):
          ui.label(t("Participants",lang)).classes("text-lg font-black")
          for p in summary["participants"]:
            with ui.row().classes("item-row w-full items-center justify-between gap-3 py-3"):
              with ui.column().classes("gap-0 flex-1"):
                ui.label(p["display_name"]).classes("font-bold")
                details=f"{p['item_total']:.2f} {currency}"
                if p.get("tip_share"): details += f" + {p['tip_share']:.2f} {t('Tip',lang).lower()}"
                ui.label(details).classes("text-xs text-slate-400")
              ui.label(f"{p['total']:.2f} {currency}").classes("font-black")
              if summary["status"] in {"settled","closed"} and p.get("payment_status")=="paid": ui.icon("paid").classes("text-emerald-600")
              if is_owner and p["role"]!="owner":
                def remind(pid=p["participant_id"], name=p["display_name"]):
                  dbr=SessionLocal()
                  try: ss=get_split_bill_session_by_token(dbr,token); send_participant_reminder(dbr,ss,user_id,pid,(f"{name}, completează plata pentru nota Pruvs." if lang=='ro' else f"{name}, please complete your Pruvs bill payment."))
                  finally: dbr.close()
                  ui.notify("Memento trimis în Pruvs." if lang=='ro' else "Pruvs reminder sent.",type="positive")
                ui.button(icon="notifications",on_click=remind).props("flat round dense").classes("text-slate-500")
                if p.get("phone_number"):
                  phone=''.join(ch for ch in p["phone_number"] if ch.isdigit() or ch=='+'); msg=(f"Salut {p['display_name']}, ai de achitat {p['total']:.2f} {currency} pentru nota Pruvs: {summary['share_url']}")
                  sms=f"sms:{phone}?body={urllib.parse.quote(msg)}"; wa=f"https://wa.me/{phone.lstrip('+')}?text={urllib.parse.quote(msg)}"
                  ui.html(f'<div class="mobile-only gap-1"><a href="{sms}" title="SMS" style="padding:7px;color:#4b5563"><span class="material-icons">sms</span></a><a href="{wa}" title="WhatsApp" style="padding:7px;color:#4b5563"><span class="material-icons">chat</span></a></div>',sanitize=False)

        if is_owner and summary["status"]=="open":
          with ui.card().classes("pruvio-card w-full p-5"):
            ui.label("Finalizează" if lang=='ro' else "Settle").classes("text-lg font-black")
            ui.label(summary["close_block_reason"] or ("Toate produsele sunt alocate." if lang=='ro' else "Everything is assigned.")).classes("text-xs text-slate-500")
            def settle():
              dbc=SessionLocal()
              try: ss=get_split_bill_session_by_token(dbc,token); close_split_bill_session(dbc,ss,user_id)
              except Exception as e: ui.notify(str(e),type="negative"); return
              finally: dbc.close()
              ui.run_javascript("window.location.reload()")
            b=ui.button(t("Settle split",lang),icon="done_all",on_click=settle).classes("pruvio-primary px-5 mt-3")
            if not summary["can_close"]: b.disable()

        if summary["status"] in {"settled","closed"} and not is_owner:
          with ui.card().classes("pruvio-card w-full p-5"):
            ui.label("Plătește proprietarul" if lang=='ro' else "Pay the owner").classes("text-lg font-black")
            ui.label((f"De plată: {current['total']:.2f} {currency}" if lang=='ro' else f"Amount due: {current['total']:.2f} {currency}")).classes("text-2xl font-black mt-1")
            ui.label(
              "Plata se face direct către proprietarul notei. Pruvs nu primește și nu redirecționează banii."
              if lang=='ro' else
              "Payment goes directly to the bill owner. Pruvs does not receive or redirect the money."
            ).classes("text-xs text-slate-500 mt-1")

            if current.get("payment_status")=="paid":
              ui.label("✓ Plată marcată ca efectuată" if lang=='ro' else "✓ Payment marked as paid").classes("text-sm font-bold text-emerald-700 mt-2")
            else:
              details=summary.get("owner_payment_details") or {}
              recipient=details.get("recipient_name")
              iban=details.get("iban")
              bank=details.get("bank_name")
              bic=details.get("bic")
              rev=details.get("revolut_payment_link")
              note=details.get("payment_note") or (f"Pruvs {token}")

              def copy_value(value, label):
                ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(value)});")
                ui.notify((f"{label} copiat." if lang=='ro' else f"{label} copied."), type="positive")

              if any([recipient, iban, bank, bic]):
                with ui.card().classes("w-full bg-slate-50 border border-slate-200 shadow-none rounded-2xl p-4 mt-3"):
                  with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Transfer bancar" if lang=='ro' else "Bank transfer").classes("font-black text-slate-900")
                    ui.icon("account_balance").classes("text-slate-400")
                  if recipient:
                    with ui.row().classes("w-full justify-between items-center gap-3"):
                      with ui.column().classes("gap-0"):
                        ui.label("Beneficiar" if lang=='ro' else "Recipient").classes("text-[11px] text-slate-400")
                        ui.label(recipient).classes("text-sm font-bold text-slate-800")
                      ui.button(icon="content_copy",on_click=lambda v=recipient:copy_value(v,"Beneficiar" if lang=='ro' else "Recipient")).props("flat round dense")
                  if iban:
                    with ui.row().classes("w-full justify-between items-center gap-3"):
                      with ui.column().classes("gap-0 min-w-0"):
                        ui.label("IBAN").classes("text-[11px] text-slate-400")
                        ui.label(iban).classes("text-sm font-mono font-bold text-slate-800 break-all")
                      ui.button(icon="content_copy",on_click=lambda v=iban:copy_value(v,"IBAN")).props("flat round dense")
                  if bank:
                    ui.label(("Bancă: " if lang=='ro' else "Bank: ")+bank).classes("text-xs text-slate-600")
                  if bic:
                    with ui.row().classes("w-full justify-between items-center gap-3"):
                      ui.label("BIC / SWIFT: "+bic).classes("text-xs text-slate-600")
                      ui.button(icon="content_copy",on_click=lambda v=bic:copy_value(v,"BIC / SWIFT")).props("flat round dense")
                  with ui.row().classes("w-full justify-between items-center gap-3"):
                    with ui.column().classes("gap-0 min-w-0"):
                      ui.label("Referință" if lang=='ro' else "Reference").classes("text-[11px] text-slate-400")
                      ui.label(note).classes("text-sm text-slate-700 break-all")
                    ui.button(icon="content_copy",on_click=lambda v=note:copy_value(v,"Referință" if lang=='ro' else "Reference")).props("flat round dense")

                  def start_bank_transfer():
                    dbp=SessionLocal()
                    try:
                      ss=get_split_bill_session_by_token(dbp,token)
                      record_participant_payment_status(dbp,ss,participant_id,"bank_transfer",False)
                    finally:
                      dbp.close()
                    ui.notify("Detaliile sunt gata pentru transfer." if lang=='ro' else "Bank details are ready to use.",type="positive")
                  if not is_owner:
                    ui.button("Folosesc transfer bancar" if lang=='ro' else "Use bank transfer",icon="account_balance",on_click=start_bank_transfer).classes("pruvio-secondary self-start px-4 mt-2")

              if rev:
                with ui.card().classes("w-full bg-slate-50 border border-slate-200 shadow-none rounded-2xl p-4 mt-3"):
                  with ui.row().classes("w-full justify-between items-center gap-3"):
                    with ui.column().classes("gap-0 min-w-0"):
                      ui.label("Revolut").classes("font-black text-slate-900")
                      ui.label(rev).classes("text-xs text-slate-500 break-all")
                    def open_revolut():
                      dbp=SessionLocal()
                      try:
                        ss=get_split_bill_session_by_token(dbp,token)
                        record_participant_payment_status(dbp,ss,participant_id,"revolut",False)
                      finally:
                        dbp.close()
                      ui.run_javascript(f"window.open({json.dumps(rev)},'_blank')")
                    ui.button("Deschide Revolut" if lang=='ro' else "Open Revolut",icon="open_in_new",on_click=open_revolut).classes("pruvio-secondary px-4")

              if not any([recipient, iban, bank, bic, rev]):
                ui.label(
                  "Proprietarul nu a salvat încă detalii pentru plată."
                  if lang=='ro' else
                  "The owner has not saved payment details yet."
                ).classes("text-sm text-amber-700 bg-amber-50 rounded-xl px-3 py-2 mt-3")

              def mark_paid():
                dbp=SessionLocal()
                try:
                  ss=get_split_bill_session_by_token(dbp,token)
                  latest=get_split_bill_session_summary(dbp,ss)
                  latest_current=next((p for p in latest.get("participants",[]) if p.get("participant_id")==participant_id),{})
                  latest_details=latest.get("owner_payment_details") or {}
                  method=latest_current.get("payment_method")
                  if method not in {"bank_transfer","revolut"}:
                    method="bank_transfer" if latest_details.get("iban") else "revolut"
                  record_participant_payment_status(dbp,ss,participant_id,method,True)
                finally:
                  dbp.close()
                ui.run_javascript("window.location.reload()")
              if not is_owner and any([iban, rev]):
                ui.button(t("Mark as paid",lang),icon="done",on_click=mark_paid).classes("pruvio-primary self-start px-5 mt-3")

        if summary["status"] in {"settled","closed"} and is_owner:
          with ui.card().classes("pruvio-card w-full p-5"):
            ui.label("Partea ta" if lang=='ro' else "Your share").classes("text-lg font-black")
            ui.label((f"{current['total']:.2f} {currency}" if lang=='ro' else f"{current['total']:.2f} {currency}")).classes("text-2xl font-black mt-1")
            ui.label(
              "Partea proprietarului este inclusă în calcul; nu trebuie să îți faci o plată. Participanții vor primi direct datele tale de plată salvate."
              if lang=='ro' else
              "The owner's share is included in the calculation; you do not need to pay yourself. Participants receive your saved payment details directly."
            ).classes("text-xs text-slate-500 mt-1")

        def poll():
          if dirty["value"]: return
          dbp=SessionLocal()
          try:
            ss=get_split_bill_session_by_token(dbp,token)
            if not ss:return
            latest=get_split_bill_session_summary(dbp,ss)
          finally: dbp.close()
          d=_summary_digest(latest)
          if d!=digest["value"]: digest["value"]=d; ui.run_javascript("window.location.reload()")
        ui.timer(1.0,poll)
