from nicegui import ui

from app.legal_content import (
    PRIVACY_SECTIONS,
    PRIVACY_TITLE,
    PRIVACY_VERSION,
    TERMS_SECTIONS,
    TERMS_TITLE,
    TERMS_VERSION,
)
from app.ui.app_shell import app_header, setup_page_head


def _render_legal(title: str, version: str, sections: list[tuple[str, str]]):
    with ui.element("main").classes("pruvio-page"):
        with ui.column().classes("pruvio-shell gap-4"):
            app_header("Legal", show_account=False)
            with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                ui.label(title).classes("text-3xl font-black text-slate-950")
                ui.label(f"Version: {version}").classes("text-xs text-slate-400")
                ui.label(
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
        setup_page_head("Terms · Pruvio")
        _render_legal(TERMS_TITLE, TERMS_VERSION, TERMS_SECTIONS)

    @ui.page("/privacy")
    def privacy_page():
        setup_page_head("Privacy · Pruvio")
        _render_legal(PRIVACY_TITLE, PRIVACY_VERSION, PRIVACY_SECTIONS)
