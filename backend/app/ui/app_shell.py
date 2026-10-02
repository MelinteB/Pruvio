import html
import os

from nicegui import ui

from app.ui.auth_state import get_logged_in_user_id, get_ui_language
from app.i18n import t


APP_CSS = r'''
:root {
  --pruvio-bg: #f5f8ff;
  --pruvio-card: #ffffff;
  --pruvio-text: #0a1435;
  --pruvio-muted: #61708b;
  --pruvio-border: #e0e8f6;
  --pruvio-accent: #0756df;
  --pruvio-accent-soft: #eaf2ff;
  --pruvio-danger: #dc2626;
}
html, body { background: var(--pruvio-bg); color: var(--pruvio-text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
body { margin: 0; }
.q-page { min-height: 100vh; }
.pruvio-page { width: 100%; min-height: 100vh; padding: 22px 16px 104px; }
.pruvio-shell { width: min(900px, 100%); margin: 0 auto; }
.pruvio-card { background: rgba(255,255,255,.98); border: 1px solid var(--pruvio-border); border-radius: 20px; box-shadow: 0 8px 30px rgba(15,23,42,.045); }
.pruvio-soft { background: #fafafa; border: 1px solid var(--pruvio-border); border-radius: 16px; }
.pruvio-primary { background: var(--pruvio-accent) !important; color: white !important; border-radius: 12px !important; font-weight: 700 !important; min-height: 40px !important; letter-spacing: -.01em; box-shadow: none !important; }
.pruvio-secondary { background: white !important; color: var(--pruvio-text) !important; border: 1px solid #d1d5db !important; border-radius: 12px !important; font-weight: 650 !important; min-height: 40px !important; box-shadow: none !important; }
.pruvio-ghost { background: transparent !important; color: #374151 !important; border-radius: 10px !important; min-height: 36px !important; box-shadow: none !important; }
.pruvio-icon-button { width: 38px !important; height: 38px !important; min-height: 38px !important; border: 1px solid #e5e7eb !important; background: #fff !important; color: #374151 !important; box-shadow: 0 1px 2px rgba(0,0,0,.03) !important; }
.pruvio-link { color: var(--pruvio-accent); font-weight: 700; text-decoration: none; cursor: pointer; }
.pruvio-link:hover { text-decoration: underline; text-underline-offset: 3px; }
.metric-pill { padding: 6px 10px; border-radius: 999px; border: 1px solid #e5e7eb; background: white; font-size: 12px; font-weight: 700; color: #4b5563; }
.metric-accent { color: #0756df; background: #eaf2ff; border-color: #c8dcff; }
.item-row { border-bottom: 1px solid #f3f4f6; }
.item-row:last-child { border-bottom: 0; }
.pruvio-login-shell { width: min(1040px, 100%); margin: 0 auto; }
.pruvio-login-card { width: min(430px, 100%); }
.pruvio-bottom-nav { position: fixed; left: 50%; transform: translateX(-50%); bottom: 12px; width: min(560px, calc(100% - 24px)); z-index: 1200; background: rgba(255,255,255,.95); border: 1px solid #e5e7eb; border-radius: 18px; box-shadow: 0 14px 34px rgba(15,23,42,.12); backdrop-filter: blur(18px); padding: 5px; }
.pruvio-bottom-button { min-width: 58px; color: #6b7280 !important; border-radius: 12px !important; }
.pruvio-bottom-active { color: var(--pruvio-accent) !important; background: #eaf2ff !important; }
.legal-copy p { margin-bottom: 10px; line-height: 1.62; color: #4b5563; }
.pruvio-logo-mark { width: 42px; height: 42px; display: block; object-fit: contain; }
.pruvio-upload-zone .q-uploader { border: 1.5px dashed #cbd5e1 !important; border-radius: 18px !important; background: #fbfcfd !important; box-shadow: none !important; width: 100% !important; }
.pruvio-upload-zone .q-uploader__header { background: transparent !important; color: var(--pruvio-text) !important; padding: 16px !important; }
.pruvio-upload-zone .q-uploader__list { min-height: 0 !important; padding: 0 14px 12px !important; }
.scan-frame { background: #0b0f18; border-radius: 18px; padding: 12px; box-shadow: inset 0 0 0 1px rgba(255,255,255,.05); overflow: hidden; }
.scan-canvas { min-height: 340px; max-height: 70vh; display:flex; align-items:center; justify-content:center; overflow:hidden; border-radius:12px; background: #090d14; }
.scan-canvas img { display:block; max-width:100%; }
.scan-toolbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; justify-content:center; padding: 10px 2px 0; }
.scan-hint { color:#9ca3af; font-size:12px; text-align:center; margin-top:8px; }
.claimed-item { background:#f3f4f6; opacity:.72; }
.claimed-item .claim-name { text-decoration: line-through; color:#9ca3af; }
.participant-badge { display:inline-flex; align-items:center; gap:4px; padding:4px 8px; border-radius:999px; background:#e5e7eb; color:#4b5563; font-size:11px; font-weight:700; }
.live-dot { width:7px; height:7px; border-radius:999px; background:#0756df; display:inline-block; box-shadow:0 0 0 4px rgba(7,86,223,.12); }
.mobile-only { display:none !important; }
body.pruvio-mobile .mobile-only { display:flex !important; }
@media (max-width: 640px) {
  .pruvio-page { padding: 14px 10px 96px; }
  .pruvio-card { border-radius: 18px; }
  .pruvio-bottom-nav { bottom: 8px; }
  .scan-canvas { min-height: 300px; }
}

.pruvs-brand-logo { display:block; max-width:100%; object-fit:contain; }
.pruvio-page .text-slate-950, .pruvio-page .text-slate-900, .q-dialog .text-slate-950 { color:var(--pruvio-text) !important; }
.pruvio-primary { transition:background .16s ease, box-shadow .16s ease; }
.pruvio-primary:hover { background:#0649be !important; box-shadow:0 5px 16px rgba(7,86,223,.16) !important; }
.pruvio-secondary:hover { background:#f0f5ff !important; border-color:#b5cdf8 !important; }
.pruvio-page .q-field--outlined .q-field__control, .q-dialog .q-field--outlined .q-field__control { border-radius:12px; }
.pruvio-page .q-field--outlined .q-field__control:before, .q-dialog .q-field--outlined .q-field__control:before { border-color:#d8e3f5; }
.pruvio-page .q-field--focused .q-field__control:after, .q-dialog .q-field--focused .q-field__control:after { border-color:var(--pruvio-accent); }
.pruvio-primary:focus-visible, .pruvio-secondary:focus-visible, .pruvio-link:focus-visible { outline:3px solid #8cb7ff; outline-offset:3px; }
.pruvio-login-card { border-top:3px solid #0756df; }
.pruvs-otp-card { border:1px solid #d9e6fb; box-shadow:0 24px 80px rgba(10,20,53,.16); }
.pruvio-otp-code input { color:#0a1435; }
'''


def setup_page_head(title: str) -> None:
    ui.page_title(title)
    ui.colors(primary='#0756df', secondary='#0a1435', accent='#1598ff',
              positive='#0f766e', negative='#b91c1c', info='#0756df', warning='#b45309')
    safe_title = html.escape(title, quote=True)
    base_url = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    share_image = html.escape(f"{base_url}/static/pruvs-512.png?v=6.5.0", quote=True)
    ui.add_head_html(
        f'''
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
        <meta name="theme-color" content="#0a1435">
        <meta name="application-name" content="Pruvs">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="default">
        <meta name="apple-mobile-web-app-title" content="Pruvs">
        <meta name="description" content="Scan receipts and split bills with Pruvs.">
        <meta property="og:site_name" content="Pruvs">
        <meta property="og:title" content="{safe_title}">
        <meta property="og:description" content="Scan receipts and split bills with Pruvs.">
        <meta property="og:type" content="website">
        <meta property="og:image" content="{share_image}">
        <meta property="og:image:width" content="512">
        <meta property="og:image:height" content="512">
        <meta name="twitter:card" content="summary">
        <meta name="twitter:title" content="{safe_title}">
        <meta name="twitter:image" content="{share_image}">
        <link rel="manifest" href="/static/manifest.webmanifest?v=6.5.0">
        <link rel="icon" type="image/png" sizes="32x32" href="/static/pruvs-32.png?v=6.5.0">
        <link rel="icon" type="image/png" sizes="192x192" href="/static/pruvs-192.png?v=6.5.0">
        <link rel="shortcut icon" href="/static/pruvs-32.png?v=6.5.0">
        <link rel="apple-touch-icon" sizes="180x180" href="/static/pruvs-180.png?v=6.5.0">
        <script>
          (function(){{
            const mobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) || (navigator.maxTouchPoints > 1 && Math.min(screen.width, screen.height) < 900);
            if (mobile) document.documentElement.classList.add('pruvio-mobile-root');
            window.addEventListener('DOMContentLoaded', () => {{ if (mobile) document.body.classList.add('pruvio-mobile'); }});
          }})();
          if ('serviceWorker' in navigator) {{
            window.addEventListener('load', () => navigator.serviceWorker.register('/static/service-worker.js?v=6.5.0'));
          }}
        </script>
        ''')
    ui.add_head_html(f"<style>{APP_CSS}</style>")


def logo_mark(size: int = 42) -> None:
    ui.html(f'<img src="/static/pruvs-mark.png" class="pruvio-logo-mark" style="width:{size}px;height:{size}px" alt="Pruvs">', sanitize=False)


def brand_logo(width: int = 164) -> None:
    ui.html(f'<img src="/static/pruvs-logo.png" class="pruvs-brand-logo" style="width:{width}px;height:auto" alt="Pruvs" fetchpriority="high">', sanitize=False)


def app_header(subtitle: str = "Receipt assistant", *, show_account: bool = True, language: str | None = None) -> None:
    lang = language or get_ui_language()
    with ui.row().classes("w-full items-center justify-between gap-3 px-1 py-1"):
        with ui.row().classes("items-center gap-3 cursor-pointer").on("click", lambda: ui.navigate.to("/")):
            with ui.column().classes("gap-0"):
                brand_logo()
                ui.label(t(subtitle, lang)).classes("text-[10px] text-slate-500 uppercase tracking-[.12em] pl-4")
        if show_account and get_logged_in_user_id() is not None:
            ui.button(icon="account_circle", on_click=lambda: ui.navigate.to("/account")).props(
                "flat round dense aria-label='Account'"
            ).classes("text-slate-500")


def bottom_nav(active: str = "home", language: str | None = None) -> None:
    if get_logged_in_user_id() is None:
        return
    lang = language or get_ui_language()
    items = [
        ("home", "home", "Home", "/"),
        ("upload", "document_scanner", "Scan", "/upload"),
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
