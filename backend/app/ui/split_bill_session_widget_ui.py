import json
from fastapi import Request
from nicegui import ui

from app.db.database import SessionLocal
from app.services.split_bill_session_service import (
    get_split_bill_session_by_token,
    get_split_bill_session_summary,
    join_split_bill_session,
    save_participant_selection,
    close_split_bill_session,
    get_split_bill_participant_by_token,
    update_expected_participants_count,
)
from app.services.onboarding_otp_service import (
    start_otp_onboarding,
    verify_phone_otp,
    verify_email_otp,
)


def load_session_summary(token: str) -> dict | None:
    db = SessionLocal()

    try:
        session = get_split_bill_session_by_token(
            db=db,
            token=token
        )

        if not session:
            return None

        return get_split_bill_session_summary(
            db=db,
            session=session
        )

    finally:
        db.close()


def setup_split_bill_session_widget_ui():

    @ui.page("/split-bill/sessions/{token}/join")
    def split_bill_join_page(token: str):
        render_join_page(token=token)

    @ui.page("/split-bill/sessions/{token}/widget-ui")
    def split_bill_widget_page(token: str, request: Request):
        participant_id_raw = request.query_params.get("participant_id")

        try:
            participant_id = int(participant_id_raw) if participant_id_raw else None
        except ValueError:
            participant_id = None

        render_widget_page(
            token=token,
            participant_id=participant_id
        )

    # Compatibility with old participant-token links.
    @ui.page("/split-bill/sessions/{token}/p/{participant_token}/widget-ui")
    def split_bill_legacy_participant_page(
        token: str,
        participant_token: str
    ):
        db = SessionLocal()

        try:
            session = get_split_bill_session_by_token(
                db=db,
                token=token
            )

            participant = get_split_bill_participant_by_token(
                db=db,
                participant_token=participant_token
            )

            if not session or not participant or participant.session_id != session.id:
                render_error_page(
                    title="Invalid participant link",
                    message="The participant link is invalid or expired."
                )
                return

            render_widget_page(
                token=token,
                participant_id=participant.id
            )

        finally:
            db.close()


def add_global_style():
    ui.page_title("Pruvio")

    ui.colors(
        primary="#111827",
        secondary="#64748b",
        accent="#10b981",
        positive="#059669",
        negative="#dc2626"
    )

    ui.add_head_html(
        """
        <style>
            :root {
                color-scheme: light;
            }

            body {
                margin: 0;
                background:
                    radial-gradient(circle at 15% -10%, rgba(16,185,129,.10), transparent 28%),
                    #f6f7f9;
                color: #111827;
            }

            .pruvio-page {
                width: 100%;
                min-height: 100vh;
                padding: 14px;
            }

            .pruvio-shell {
                width: 100%;
                max-width: 980px;
                margin: 0 auto;
            }

            .pruvio-card {
                border-radius: 22px;
                border: 1px solid rgba(226,232,240,.9);
                background: rgba(255,255,255,.92);
                box-shadow: 0 10px 32px rgba(15,23,42,.055);
                backdrop-filter: blur(16px);
            }

            .metric-pill {
                padding: 8px 11px;
                border-radius: 999px;
                background: #f8fafc;
                border: 1px solid #e5e7eb;
                color: #334155;
                font-size: 12px;
                font-weight: 800;
            }

            .metric-pill-accent {
                background: #ecfdf5;
                border-color: #d1fae5;
                color: #047857;
            }

            .item-row {
                border-bottom: 1px solid #f1f5f9;
                transition: background .16s ease;
            }

            .item-row:last-child {
                border-bottom: 0;
            }

            .item-row:hover {
                background: rgba(248,250,252,.72);
            }

            .compact-btn {
                min-height: 40px;
                padding: 0 16px;
                border-radius: 13px;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: -.01em;
                box-shadow: none;
            }

            .compact-btn-primary {
                background: #111827;
                color: white;
            }

            .compact-btn-secondary {
                background: #f8fafc;
                color: #334155;
                border: 1px solid #e2e8f0;
            }

            @media (max-width: 700px) {
                .pruvio-page {
                    padding: 10px;
                }
                .pruvio-card {
                    border-radius: 18px;
                }
            }
        </style>
        """
    )


def render_error_page(title: str, message: str):
    add_global_style()

    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            with ui.card().classes("pruvio-card w-full p-6"):
                ui.label(title).classes(
                    "text-2xl font-black text-red-700"
                )
                ui.label(message).classes(
                    "text-slate-500 mt-2"
                )


def render_join_page(token: str):
    add_global_style()

    summary = load_session_summary(token)

    if not summary:
        render_error_page(
            title="Split bill not found",
            message="The link is invalid or expired."
        )
        return

    if summary["status"] != "open":
        render_error_page(
            title="Split bill is closed",
            message="This bill session is no longer open."
        )
        return

    phone_verified = False
    email_required = False
    current_phone = None
    current_name = None
    current_email = None

    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):

            with ui.row().classes("w-full items-center justify-between gap-3"):
                with ui.row().classes("items-center gap-3"):
                    ui.label("P").classes(
                        "w-11 h-11 rounded-2xl bg-slate-900 text-white "
                        "font-black text-xl flex items-center justify-center shadow-lg"
                    )

                    with ui.column().classes("gap-0"):
                        ui.label("Pruvio").classes(
                            "text-lg font-black text-slate-900 leading-tight"
                        )
                        ui.label("Join shared split bill").classes(
                            "text-xs text-slate-500"
                        )

                ui.label(f"Session #{summary['session_id']}").classes(
                    "hidden sm:block px-3 py-2 rounded-full bg-white "
                    "border border-slate-200 text-xs text-slate-500 shadow-sm"
                )

            with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                ui.label("Ai fost invitat sa imparti o nota").classes(
                    "text-3xl sm:text-5xl font-black text-slate-900 "
                    "tracking-tight leading-tight"
                )

                ui.label(
                    "Pentru a continua, confirma numarul de telefon. "
                    "Daca nu ai cont Pruvio activ, iti trimitem un cod OTP."
                ).classes("text-sm sm:text-base text-slate-500 mt-2")

                with ui.row().classes("gap-3 mt-5 flex-wrap"):
                    ui.label(
                        f"Total bon: {summary['bill_total']:.2f} {summary['currency']}"
                    ).classes("px-4 py-3 rounded-2xl bg-slate-100 font-black")

                    ui.label(
                        f"Participanti: {summary['joined_participants_count']} / "
                        f"{summary['expected_participants_count']}"
                    ).classes("px-4 py-3 rounded-2xl bg-slate-100 font-black")

                    ui.label(
                        f"Ramas: {summary['remaining_total']:.2f} {summary['currency']}"
                    ).classes("px-4 py-3 rounded-2xl bg-green-50 text-green-700 font-black")

            with ui.row().classes("w-full gap-4 items-start flex-col lg:flex-row"):

                with ui.card().classes("pruvio-card w-full lg:flex-1 p-5"):
                    ui.label("Continua cu Pruvio").classes(
                        "text-xl font-black text-slate-900"
                    )

                    ui.label(
                        "Introdu numarul tau de WhatsApp. Daca esti deja activ "
                        "in Pruvio, intri direct in nota. Daca nu, verificam prin OTP."
                    ).classes("text-sm text-slate-500 mb-3")

                    name_input = ui.input(
                        label="Numele tau",
                        placeholder="Ex: Ada"
                    ).classes("w-full").props("outlined")

                    phone_input = ui.input(
                        label="Telefon WhatsApp",
                        placeholder="+407xxxxxxxx"
                    ).classes("w-full").props("outlined")

                    email_input = ui.input(
                        label="Email optional",
                        placeholder="ada@example.com"
                    ).classes("w-full").props("outlined")

                    terms_checkbox = ui.checkbox(
                        "Accept termenii Pruvio si confirm ca acest numar imi apartine."
                    ).classes("mt-2")

                    status_label = ui.label("").classes(
                        "text-sm text-slate-500 mt-2"
                    )

                    debug_label = ui.label("").classes(
                        "text-xs text-orange-700 font-bold mt-2"
                    )

                    otp_card = ui.card().classes(
                        "w-full shadow-none border border-slate-200 rounded-2xl p-4 mt-4"
                    )
                    otp_card.visible = False

                    with otp_card:
                        ui.label("Verificare OTP").classes(
                            "text-lg font-black text-slate-900"
                        )

                        ui.label(
                            "Introdu codul primit pe WhatsApp. "
                            "Daca ai completat si email, verifica si codul de email."
                        ).classes("text-sm text-slate-500")

                        phone_code_input = ui.input(
                            label="Cod OTP WhatsApp",
                            placeholder="123456"
                        ).classes("w-full mt-3").props("outlined")

                        phone_verify_status = ui.label("").classes(
                            "text-sm text-slate-500"
                        )

                        email_code_input = ui.input(
                            label="Cod OTP Email",
                            placeholder="654321"
                        ).classes("w-full mt-3").props("outlined")
                        email_code_input.visible = False

                        email_verify_status = ui.label("").classes(
                            "text-sm text-slate-500"
                        )
                        email_verify_status.visible = False

                    def join_active_user():
                        nonlocal current_phone, current_name

                        db = SessionLocal()

                        try:
                            session = get_split_bill_session_by_token(
                                db=db,
                                token=token
                            )

                            if not session:
                                ui.notify(
                                    "Split bill session not found.",
                                    type="negative",
                                    position="top"
                                )
                                return

                            result = join_split_bill_session(
                                db=db,
                                session=session,
                                phone_number=current_phone,
                                display_name=current_name
                            )

                        finally:
                            db.close()

                        if result["status"] in {"joined", "already_joined"}:
                            ui.notify(
                                result["message"],
                                type="positive",
                                position="top"
                            )
                            ui.navigate.to(result["widget_url"])
                            return

                        ui.notify(
                            result["message"],
                            type="warning",
                            position="top"
                        )
                        status_label.set_text(result["message"])

                    def continue_or_start_otp():
                        nonlocal current_phone, current_name, current_email
                        nonlocal email_required

                        current_name = (name_input.value or "").strip()
                        current_phone = (phone_input.value or "").strip()
                        current_email = (email_input.value or "").strip() or None

                        if not current_phone:
                            ui.notify(
                                "Introdu numarul de telefon.",
                                type="warning",
                                position="top"
                            )
                            return

                        if not current_name:
                            ui.notify(
                                "Introdu numele tau.",
                                type="warning",
                                position="top"
                            )
                            return

                        db = SessionLocal()

                        try:
                            session = get_split_bill_session_by_token(
                                db=db,
                                token=token
                            )

                            result = join_split_bill_session(
                                db=db,
                                session=session,
                                phone_number=current_phone,
                                display_name=current_name
                            )

                        finally:
                            db.close()

                        if result["status"] in {"joined", "already_joined"}:
                            ui.notify(
                                result["message"],
                                type="positive",
                                position="top"
                            )
                            ui.navigate.to(result["widget_url"])
                            return

                        if result["status"] not in {"requires_onboarding"}:
                            ui.notify(
                                result["message"],
                                type="warning",
                                position="top"
                            )
                            status_label.set_text(result["message"])
                            return

                        if not terms_checkbox.value:
                            ui.notify(
                                "Pentru onboarding trebuie sa accepti termenii.",
                                type="warning",
                                position="top"
                            )
                            status_label.set_text(
                                "Accepta termenii pentru a primi codul OTP."
                            )
                            return

                        db_otp = SessionLocal()

                        try:
                            otp_result = start_otp_onboarding(
                                db=db_otp,
                                phone_number=current_phone,
                                display_name=current_name,
                                email=current_email,
                                accepted_terms=True
                            )

                        except ValueError as error:
                            ui.notify(
                                str(error),
                                type="negative",
                                position="top"
                            )
                            return

                        finally:
                            db_otp.close()

                        email_required = bool(current_email)

                        otp_card.visible = True
                        email_code_input.visible = email_required
                        email_verify_status.visible = email_required

                        status_label.set_text(
                            "OTP trimis. Verifica WhatsApp"
                            + (" si email." if email_required else ".")
                        )

                        debug_parts = []

                        if otp_result.get("debug_phone_otp"):
                            debug_parts.append(
                                f"DEV WhatsApp OTP: {otp_result['debug_phone_otp']}"
                            )

                        if otp_result.get("debug_email_otp"):
                            debug_parts.append(
                                f"DEV Email OTP: {otp_result['debug_email_otp']}"
                            )

                        debug_label.set_text(" | ".join(debug_parts))

                        ui.notify(
                            "Cod OTP trimis.",
                            type="positive",
                            position="top"
                        )

                    def verify_phone_code():
                        nonlocal phone_verified

                        code = (phone_code_input.value or "").strip()

                        if not code:
                            ui.notify(
                                "Introdu codul primit pe WhatsApp.",
                                type="warning",
                                position="top"
                            )
                            return

                        db = SessionLocal()

                        try:
                            result = verify_phone_otp(
                                db=db,
                                phone_number=current_phone,
                                code=code
                            )

                        except ValueError as error:
                            ui.notify(
                                str(error),
                                type="negative",
                                position="top"
                            )
                            return

                        finally:
                            db.close()

                        phone_verified = True
                        phone_verify_status.set_text(result["message"])
                        phone_verify_status.classes(
                            "text-green-700 font-bold",
                            remove="text-slate-500 text-red-700"
                        )

                        if result["status"] == "active":
                            join_active_user()
                            return

                        if email_required:
                            ui.notify(
                                "Telefon verificat. Acum verifica emailul.",
                                type="positive",
                                position="top"
                            )
                        else:
                            ui.notify(
                                result["message"],
                                type="warning",
                                position="top"
                            )

                    def verify_email_code():
                        if not phone_verified:
                            ui.notify(
                                "Verifica intai telefonul.",
                                type="warning",
                                position="top"
                            )
                            return

                        code = (email_code_input.value or "").strip()

                        if not code:
                            ui.notify(
                                "Introdu codul primit pe email.",
                                type="warning",
                                position="top"
                            )
                            return

                        db = SessionLocal()

                        try:
                            result = verify_email_otp(
                                db=db,
                                email=current_email,
                                code=code
                            )

                        except ValueError as error:
                            ui.notify(
                                str(error),
                                type="negative",
                                position="top"
                            )
                            return

                        finally:
                            db.close()

                        email_verify_status.set_text(result["message"])
                        email_verify_status.classes(
                            "text-green-700 font-bold",
                            remove="text-slate-500 text-red-700"
                        )

                        if result["status"] == "active":
                            join_active_user()
                            return

                        ui.notify(
                            result["message"],
                            type="warning",
                            position="top"
                        )

                    ui.button(
                        "Continua",
                        on_click=continue_or_start_otp
                    ).classes(
                        "rounded-2xl bg-slate-900 text-white font-black px-6 mt-4"
                    )

                    with otp_card:
                        with ui.row().classes("gap-2 mt-3 flex-wrap"):
                            ui.button(
                                "Verifica telefon",
                                on_click=verify_phone_code
                            ).classes(
                                "rounded-2xl bg-slate-900 text-white font-black px-5"
                            )

                            ui.button(
                                "Verifica email",
                                on_click=verify_email_code
                            ).props("outline").classes(
                                "rounded-2xl font-black px-5"
                            )

                with ui.card().classes("pruvio-card w-full lg:w-[370px] p-5"):
                    ui.label("Status nota").classes(
                        "text-lg font-black text-slate-900"
                    )

                    ui.label(
                        f"Participanti conectati: "
                        f"{summary['joined_participants_count']} / "
                        f"{summary['expected_participants_count']}"
                    ).classes("mt-3 font-bold text-slate-700")

                    ui.label(
                        f"Participanti lipsa: {summary['missing_participants_count']}"
                    ).classes("font-bold text-slate-700")

                    ui.label(
                        f"Ramas de asignat: "
                        f"{summary['remaining_total']:.2f} {summary['currency']}"
                    ).classes("font-black text-green-700 mt-2")

                    ui.separator().classes("my-4")

                    ui.label("Participanti").classes(
                        "text-sm font-black text-slate-700"
                    )

                    if not summary["participants"]:
                        ui.label("Niciun participant inca.").classes(
                            "text-sm text-slate-500"
                        )
                    else:
                        for participant in summary["participants"]:
                            with ui.row().classes(
                                "w-full justify-between items-center mt-2"
                            ):
                                ui.label(participant["display_name"]).classes(
                                    "font-bold"
                                )
                                ui.label(
                                    f"{participant['total']:.2f} {summary['currency']}"
                                ).classes("font-black")


def render_widget_page(
    token: str,
    participant_id: int | None
):
    add_global_style()

    summary = load_session_summary(token)

    if not summary:
        render_error_page(
            title="Nota nu a fost gasita",
            message="Linkul este invalid sau a expirat."
        )
        return

    if participant_id is None:
        ui.navigate.to(f"/split-bill/sessions/{token}/join")
        return

    current_participant = None

    for participant in summary["participants"]:
        if participant["participant_id"] == participant_id:
            current_participant = participant
            break

    if not current_participant:
        render_error_page(
            title="Participant negasit",
            message="Nu esti conectat la aceasta nota."
        )
        return

    currency = summary["currency"]
    is_owner = current_participant["role"] == "owner"
    selected_item_ids = {
        item["item_id"]
        for item in summary["items"]
        if item["participant_id"] == participant_id
    }

    def reload_page():
        ui.navigate.to(
            f"/split-bill/sessions/{token}/widget-ui?participant_id={participant_id}"
        )

    def split_item_label(name: str) -> tuple[str, str | None]:
        marker = " | Reducere "
        if marker not in name:
            return name, None
        base_name, discount = name.split(marker, 1)
        return base_name, f"Reducere {discount}"

    share_url = summary["share_url"]
    share_message = (
        "Te invit sa impartim nota in Pruvio. "
        "Deschide linkul si alege produsele tale."
    )

    def share_invitation():
        script = f"""
        (() => {{
            const data = {{
                title: 'Pruvio',
                text: {json.dumps(share_message)},
                url: {json.dumps(share_url)}
            }};
            if (navigator.share) {{
                navigator.share(data).catch(() => {{}});
            }} else if (navigator.clipboard) {{
                navigator.clipboard.writeText(data.text + '\\n' + data.url);
            }}
        }})();
        """
        ui.run_javascript(script)

    def copy_invitation():
        text_to_copy = f"{share_message}\n{share_url}"
        ui.run_javascript(
            f"navigator.clipboard.writeText({json.dumps(text_to_copy)})"
        )
        ui.notify("Link copiat.", type="positive", position="top")

    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-3"):

            with ui.row().classes("w-full items-center justify-between gap-3 px-1"):
                with ui.row().classes("items-center gap-3"):
                    ui.label("P").classes(
                        "w-10 h-10 rounded-xl bg-slate-950 text-white "
                        "font-black text-lg flex items-center justify-center"
                    )
                    with ui.column().classes("gap-0"):
                        ui.label("Pruvio").classes(
                            "text-base font-black text-slate-950 leading-tight"
                        )
                        ui.label("Split bill").classes(
                            "text-[11px] text-slate-500 tracking-wide uppercase"
                        )

                status_text = "Deschisa" if summary["status"] == "open" else "Inchisa"
                ui.label(status_text).classes(
                    "px-3 py-1.5 rounded-full bg-white border border-slate-200 "
                    "text-xs font-bold text-slate-600"
                )

            with ui.card().classes("pruvio-card w-full p-5 sm:p-6"):
                with ui.row().classes(
                    "w-full items-start justify-between gap-5 flex-col md:flex-row"
                ):
                    with ui.column().classes("gap-1"):
                        ui.label(
                            f"Salut, {current_participant['display_name']}"
                        ).classes(
                            "text-2xl sm:text-3xl font-black text-slate-950 tracking-tight"
                        )
                        ui.label(
                            "Alege produsele tale. Modificarile raman sincronizate cu ceilalti participanti."
                        ).classes("text-sm text-slate-500 max-w-2xl")

                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.label(
                            f"{summary['bill_total']:.2f} {currency}"
                        ).classes("metric-pill")
                        ui.label(
                            f"Ramas {summary['remaining_total']:.2f} {currency}"
                        ).classes("metric-pill metric-pill-accent")
                        ui.label(
                            f"{summary['joined_participants_count']}/{summary['expected_participants_count']} persoane"
                        ).classes("metric-pill")

                progress_value = 0.0
                if summary["bill_total"]:
                    progress_value = min(
                        1.0,
                        max(0.0, summary["assigned_total"] / summary["bill_total"])
                    )

                ui.linear_progress(value=progress_value).classes(
                    "w-full mt-4 rounded-full h-2"
                )

            if is_owner and summary["status"] == "open":
                with ui.card().classes("pruvio-card w-full p-4 sm:p-5"):
                    with ui.row().classes(
                        "w-full items-center justify-between gap-4 flex-col md:flex-row"
                    ):
                        with ui.column().classes("gap-0"):
                            ui.label("Invita participantii").classes(
                                "text-base font-black text-slate-950"
                            )
                            ui.label(
                                "Alege numarul total de persoane, inclusiv tu, apoi distribuie invitatia."
                            ).classes("text-xs text-slate-500")

                        with ui.row().classes("items-end gap-2 flex-wrap justify-end"):
                            participant_count_input = ui.number(
                                label="Participanti",
                                value=summary["expected_participants_count"],
                                min=summary["joined_participants_count"],
                                max=20,
                                step=1,
                            ).props("outlined dense").classes("w-32")

                            def save_participant_count():
                                try:
                                    new_count = int(participant_count_input.value or 0)
                                except (TypeError, ValueError):
                                    ui.notify("Numar invalid.", type="warning", position="top")
                                    return

                                db = SessionLocal()
                                try:
                                    session = get_split_bill_session_by_token(db=db, token=token)
                                    update_expected_participants_count(
                                        db=db,
                                        session=session,
                                        owner_user_id=current_participant["user_id"],
                                        expected_participants_count=new_count,
                                    )
                                except ValueError as error:
                                    ui.notify(str(error), type="negative", position="top")
                                    return
                                finally:
                                    db.close()

                                ui.notify("Numarul de participanti a fost actualizat.", type="positive", position="top")
                                reload_page()

                            ui.button(
                                "Salveaza",
                                on_click=save_participant_count,
                            ).classes("compact-btn compact-btn-secondary")

                            ui.button(
                                "Distribuie",
                                icon="ios_share",
                                on_click=share_invitation,
                            ).classes("compact-btn compact-btn-primary")

                            ui.button(
                                icon="content_copy",
                                on_click=copy_invitation,
                            ).props("flat round").classes("text-slate-600")

            with ui.row().classes("w-full gap-3 items-start flex-col lg:flex-row"):
                with ui.card().classes("pruvio-card w-full lg:flex-1 p-0 overflow-hidden"):
                    with ui.row().classes(
                        "w-full items-center justify-between px-4 sm:px-5 py-4 border-b border-slate-100"
                    ):
                        with ui.column().classes("gap-0"):
                            ui.label("Produse").classes("text-base font-black text-slate-950")
                            ui.label("Selecteaza ce ai consumat").classes("text-xs text-slate-500")

                        my_total_label = ui.label("").classes(
                            "text-sm font-black text-emerald-700"
                        )

                    with ui.column().classes("w-full gap-0"):
                        def refresh_my_total():
                            my_total = sum(
                                float(item["total_price"] or 0)
                                for item in summary["items"]
                                if item["item_id"] in selected_item_ids
                            )
                            my_total_label.set_text(
                                f"Al tau · {my_total:.2f} {currency}"
                            )

                        def toggle_item(item_id: int, checked: bool):
                            if checked:
                                selected_item_ids.add(item_id)
                            else:
                                selected_item_ids.discard(item_id)
                            refresh_my_total()

                        for item in summary["items"]:
                            item_id = item["item_id"]
                            assigned_to = item["assigned_to"]
                            assigned_participant_id = item["participant_id"]
                            is_assigned = item["status"] == "assigned"
                            is_mine = assigned_participant_id == participant_id
                            disabled = (
                                summary["status"] != "open"
                                or (is_assigned and not is_mine)
                            )

                            product_name, discount_text = split_item_label(item["name"])

                            with ui.row().classes(
                                "item-row w-full items-center gap-3 px-4 sm:px-5 py-3.5"
                            ):
                                checkbox = ui.checkbox(
                                    value=is_mine,
                                    on_change=lambda e, item_id=item_id: toggle_item(
                                        item_id=item_id,
                                        checked=e.value,
                                    )
                                ).props("dense")

                                if disabled:
                                    checkbox.disable()

                                with ui.column().classes("gap-0 flex-1 min-w-0"):
                                    ui.label(product_name).classes(
                                        "text-sm font-bold text-slate-900 leading-snug"
                                    )

                                    status_parts = []
                                    if discount_text:
                                        status_parts.append(discount_text)
                                    if is_mine:
                                        status_parts.append("Selectat de tine")
                                    elif assigned_to:
                                        status_parts.append(f"{assigned_to}")

                                    if status_parts:
                                        ui.label(" · ".join(status_parts)).classes(
                                            "text-[11px] text-slate-500"
                                        )

                                ui.label(
                                    f"{item['total_price']:.2f} {currency}"
                                ).classes("text-sm font-black text-slate-950 whitespace-nowrap")

                        refresh_my_total()

                with ui.column().classes("w-full lg:w-[300px] gap-3 lg:sticky lg:top-3"):
                    with ui.card().classes("pruvio-card w-full p-4 sm:p-5"):
                        ui.label("Nota ta").classes("text-base font-black text-slate-950")

                        with ui.row().classes("w-full justify-between mt-3"):
                            ui.label("Alocat").classes("text-sm text-slate-500")
                            ui.label(
                                f"{summary['assigned_total']:.2f} {currency}"
                            ).classes("text-sm font-bold")

                        with ui.row().classes("w-full justify-between"):
                            ui.label("Ramas").classes("text-sm text-slate-500")
                            ui.label(
                                f"{summary['remaining_total']:.2f} {currency}"
                            ).classes("text-sm font-black text-emerald-700")

                        if summary["status"] == "open":
                            def save_my_selection():
                                db = SessionLocal()
                                try:
                                    session = get_split_bill_session_by_token(db=db, token=token)
                                    save_participant_selection(
                                        db=db,
                                        session=session,
                                        participant_id=participant_id,
                                        selected_item_ids=list(selected_item_ids),
                                    )
                                except ValueError as error:
                                    ui.notify(str(error), type="negative", position="top")
                                    return
                                finally:
                                    db.close()

                                ui.notify("Selectia a fost salvata.", type="positive", position="top")
                                reload_page()

                            ui.button(
                                "Salveaza selectia",
                                on_click=save_my_selection,
                            ).classes("compact-btn compact-btn-primary w-full mt-4")

                        if is_owner:
                            def close_session():
                                db = SessionLocal()
                                try:
                                    session = get_split_bill_session_by_token(db=db, token=token)
                                    close_split_bill_session(
                                        db=db,
                                        session=session,
                                        owner_user_id=current_participant["user_id"],
                                    )
                                except ValueError as error:
                                    ui.notify(str(error), type="negative", position="top")
                                    return
                                finally:
                                    db.close()

                                ui.notify("Nota a fost inchisa.", type="positive", position="top")
                                reload_page()

                            close_button = ui.button(
                                "Inchide nota",
                                on_click=close_session,
                            ).props("flat").classes("w-full text-xs mt-2 text-slate-500")

                            if not summary["can_close"]:
                                close_button.disable()

                            if summary["close_block_reason"]:
                                ui.label(summary["close_block_reason"]).classes(
                                    "text-[11px] text-amber-700 mt-1 leading-snug"
                                )

                    with ui.card().classes("pruvio-card w-full p-4 sm:p-5"):
                        ui.label("Participanti").classes("text-sm font-black text-slate-950")

                        for participant in summary["participants"]:
                            with ui.row().classes(
                                "w-full items-center justify-between gap-2 py-2 border-b border-slate-100 last:border-0"
                            ):
                                with ui.row().classes("items-center gap-2 min-w-0"):
                                    initial = (participant["display_name"] or "?").strip()[:1].upper()
                                    ui.label(initial).classes(
                                        "w-7 h-7 rounded-full bg-slate-100 text-slate-700 "
                                        "text-xs font-black flex items-center justify-center"
                                    )
                                    name = participant["display_name"]
                                    if participant["role"] == "owner":
                                        name = f"{name} · tu"
                                    ui.label(name).classes("text-xs font-bold truncate")

                                ui.label(
                                    f"{participant['total']:.2f} {currency}"
                                ).classes("text-xs font-black whitespace-nowrap")
