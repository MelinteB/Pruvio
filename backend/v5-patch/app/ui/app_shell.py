from nicegui import ui

from app.ui.auth_state import get_logged_in_user_id, get_ui_language
from app.i18n import t


APP_CSS = r'''
:root {
  --pruvio-bg: #f7f8fb;
  --pruvio-card: #ffffff;
  --pruvio-text: #0f172a;
  --pruvio-muted: #64748b;
  --pruvio-border: #e2e8f0;
  --pruvio-accent: #10b981;
}
body { background: var(--pruvio-bg); color: var(--pruvio-text); }
.q-page { min-height: 100vh; }
.pruvio-page { width: 100%; min-height: 100vh; padding: 18px 14px 104px; }
.pruvio-shell { width: min(920px, 100%); margin: 0 auto; }
.pruvio-card { background: white; border: 1px solid var(--pruvio-border); border-radius: 24px; box-shadow: 0 12px 35px rgba(15,23,42,.06); }
.pruvio-soft { background: #f8fafc; border: 1px solid var(--pruvio-border); border-radius: 18px; }
.pruvio-primary { background: #0f172a !important; color: white !important; border-radius: 16px !important; font-weight: 800 !important; }
.pruvio-secondary { background: white !important; color: #0f172a !important; border: 1px solid #cbd5e1 !important; border-radius: 16px !important; font-weight: 800 !important; }
.pruvio-link { color: #0f172a; font-weight: 800; text-decoration: underline; text-underline-offset: 3px; cursor: pointer; }
.metric-pill { padding: 7px 11px; border-radius: 999px; border: 1px solid #e2e8f0; background: white; font-size: 12px; font-weight: 800; color: #475569; }
.metric-accent { color: #047857; background: #ecfdf5; border-color: #a7f3d0; }
.item-row { border-bottom: 1px solid #f1f5f9; }
.item-row:last-child { border-bottom: 0; }
.pruvio-login-shell { width: min(1080px, 100%); margin: 0 auto; }
.pruvio-login-card { width: min(440px, 100%); }
.pruvio-bottom-nav { position: fixed; left: 50%; transform: translateX(-50%); bottom: 12px; width: min(620px, calc(100% - 20px)); z-index: 1200; background: rgba(255,255,255,.96); border: 1px solid #e2e8f0; border-radius: 22px; box-shadow: 0 18px 45px rgba(15,23,42,.16); backdrop-filter: blur(16px); padding: 7px; }
.pruvio-bottom-button { min-width: 64px; color: #475569 !important; border-radius: 14px !important; }
.pruvio-bottom-active { color: #0f172a !important; background: #f1f5f9 !important; }
.legal-copy p { margin-bottom: 10px; line-height: 1.55; color: #475569; }
@media (max-width: 640px) {
  .pruvio-page { padding: 12px 10px 98px; }
  .pruvio-card { border-radius: 20px; }
  .pruvio-bottom-nav { bottom: 8px; }
}
'''


def setup_page_head(title: str) -> None:
    ui.page_title(title)
    ui.add_head_html(
        '''
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
        <meta name="theme-color" content="#0f172a">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="default">
        <meta name="apple-mobile-web-app-title" content="Pruvio">
        <link rel="manifest" href="/static/manifest.webmanifest">
        <link rel="apple-touch-icon" href="/static/pruvio-192.png">
        <script>
          if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => navigator.serviceWorker.register('/static/service-worker.js'));
          }
        </script>
        ''')
    ui.add_head_html(f"<style>{APP_CSS}</style>")


def app_header(subtitle: str = "Receipt assistant", *, show_account: bool = True, language: str | None = None) -> None:
    lang = language or get_ui_language()
    with ui.row().classes("w-full items-center justify-between gap-3 px-1"):
        with ui.row().classes("items-center gap-3 cursor-pointer").on("click", lambda: ui.navigate.to("/")):
            ui.label("P").classes(
                "w-11 h-11 rounded-2xl bg-slate-950 text-white font-black text-xl "
                "flex items-center justify-center shadow-lg"
            )
            with ui.column().classes("gap-0"):
                ui.label("Pruvio").classes("text-lg font-black text-slate-950 leading-tight")
                ui.label(t(subtitle, lang)).classes("text-[11px] text-slate-500 uppercase tracking-wide")
        if show_account and get_logged_in_user_id() is not None:
            ui.button(icon="account_circle", on_click=lambda: ui.navigate.to("/account")).props(
                "flat round aria-label='Account'"
            ).classes("text-slate-600")


def bottom_nav(active: str = "home", language: str | None = None) -> None:
    if get_logged_in_user_id() is None:
        return
    lang = language or get_ui_language()
    items = [
        ("home", "home", "Home", "/"),
        ("upload", "photo_camera", "Scan", "/upload"),
        ("history", "receipt_long", "History", "/history"),
        ("account", "person", "Account", "/account"),
    ]
    with ui.row().classes("pruvio-bottom-nav items-center justify-around gap-1"):
        for key, icon, label, target in items:
            classes = "pruvio-bottom-button"
            if key == active:
                classes += " pruvio-bottom-active"
            ui.button(t(label, lang), icon=icon, on_click=lambda target=target: ui.navigate.to(target)).props(
                "flat no-caps stack dense"
            ).classes(classes)


def display_item_name(item: dict) -> str:
    original = str(item.get("name") or item.get("original_name") or "Unnamed item").strip()
    translated = str(item.get("translated_name") or "").strip()
    if translated and translated.casefold() != original.casefold():
        return f"{original} ({translated})"
    return original


def is_integer_quantity(value: float) -> bool:
    return value >= 1 and abs(value - round(value)) < 1e-6


def quantity_text(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")
