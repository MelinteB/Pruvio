from nicegui import ui

from app.db.database import SessionLocal
from app.legal_content import (
    PRIVACY_SECTIONS,
    PRIVACY_SECTIONS_RO,
    PRIVACY_TITLE,
    PRIVACY_TITLE_RO,
    PRIVACY_VERSION,
    TERMS_SECTIONS,
    TERMS_SECTIONS_RO,
    TERMS_TITLE,
    TERMS_TITLE_RO,
    TERMS_VERSION,
)
from app.ui.app_shell import app_header, setup_page_head
from app.ui.auth_state import get_logged_in_user, get_ui_language


def _language() -> str:
    db = SessionLocal()
    try:
        user = get_logged_in_user(db)
        return (user.preferred_language if user else get_ui_language()) or "en"
    finally:
        db.close()


def _render_legal(title: str, version: str, sections: list[tuple[str, str]], lang: str):
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Legal" if lang == "en" else "Legal", show_account=False, language=lang)
            with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                ui.label(title).classes("text-3xl font-black text-slate-950")
                ui.label(f"{'Versiune' if lang == 'ro' else 'Version'}: {version}").classes("text-xs text-slate-400")
                ui.label(
                    "Draft pentru testarea produsului. Documentul trebuie revizuit de un specialist juridic înainte de lansarea comercială."
                    if lang == "ro" else
                    "Draft for product testing. This document must be reviewed by qualified legal counsel before commercial launch."
                ).classes("text-sm text-amber-700 mt-2")
                ui.separator().classes("my-4")
                with ui.column().classes("gap-5"):
                    for heading, body in sections:
                        with ui.column().classes("gap-1"):
                            ui.label(heading).classes("text-base font-black text-slate-900")
                            ui.label(body).classes("text-sm text-slate-600 leading-relaxed")


def setup_legal_ui() -> None:
    @ui.page("/terms")
    def terms_page():
        lang = _language()
        setup_page_head("Termeni · Pruvio" if lang == "ro" else "Terms · Pruvio")
        _render_legal(TERMS_TITLE_RO if lang == "ro" else TERMS_TITLE, TERMS_VERSION, TERMS_SECTIONS_RO if lang == "ro" else TERMS_SECTIONS, lang)

    @ui.page("/privacy")
    def privacy_page():
        lang = _language()
        setup_page_head("Confidențialitate · Pruvio" if lang == "ro" else "Privacy · Pruvio")
        _render_legal(PRIVACY_TITLE_RO if lang == "ro" else PRIVACY_TITLE, PRIVACY_VERSION, PRIVACY_SECTIONS_RO if lang == "ro" else PRIVACY_SECTIONS, lang)
