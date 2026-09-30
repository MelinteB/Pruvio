import os

from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.ui.app_shell import app_header, setup_page_head
from app.ui.auth_state import get_logged_in_user, get_ui_language


def setup_support_ui() -> None:
    @ui.page("/support")
    def support_page():
        db = SessionLocal()
        try:
            user = get_logged_in_user(db)
            lang = (user.preferred_language if user else get_ui_language()) or "en"
        finally:
            db.close()
        setup_page_head(f"{t('Help', lang)} · Pruvio")
        support_email = os.getenv("PRUVIO_SUPPORT_EMAIL", "support@pruvio.app")
        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Help & Support", show_account=False, language=lang)
                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label(t("Help & Support", lang)).classes("text-3xl font-black text-slate-950")
                    ui.label("Întrebări frecvente pentru versiunea curentă Pruvio." if lang == "ro" else "Common questions for the current Pruvio test version.").classes("text-sm text-slate-500")
                    if lang == "ro":
                        faqs = [
                            ("De ce sunt necesare două coduri la înregistrare?", "Pruvio verifică atât telefonul, cât și emailul pentru a confirma canalele de contact și recuperare."),
                            ("Cum îmi resetez parola?", "Folosește opțiunea Ai uitat parola? și confirmă resetarea cu OTP trimis la emailul verificat."),
                            ("De ce poate greși OCR-ul?", "Extragerea și traducerea sunt automate. Verifică întotdeauna cantitățile, prețurile, moneda și totalul."),
                            ("Prietenii au nevoie de cont pentru split?", "Nu. Pot folosi linkul partajat și introduce doar un nume pentru sesiunea curentă."),
                            ("Pruvio procesează plăți?", "Nu în această etapă. Pruvio calculează și coordonează sumele; aplicația curentă nu procesează plăți."),
                            ("Cum îmi protejez contul?", "Nu divulga codurile OTP. Folosește passkey unde este posibil și deconectează-te de pe dispozitive partajate."),
                        ]
                    else:
                        faqs = [
                            ("Why do I need two verification codes?", "Pruvio verifies both phone and email during registration so each recovery/contact channel belongs to you."),
                            ("How do I reset my password?", "Use Forgot password and confirm the reset with an OTP sent to your verified email."),
                            ("Why can OCR be wrong?", "Receipt extraction and translation are automated. Always review quantities, prices, currency and totals before splitting a bill."),
                            ("Do friends need accounts to join a split?", "No. A participant can use the share link and enter a display name for the current split session."),
                            ("Does Pruvio move money?", "Not in this stage. Pruvio calculates and coordinates amounts; payments are not processed by the current app."),
                            ("How do I protect my account?", "Never share OTP codes. Use a passkey where possible and sign out on shared devices."),
                        ]
                    with ui.column().classes("gap-4 mt-4"):
                        for q, a in faqs:
                            with ui.expansion(q).classes("w-full border border-slate-200 rounded-xl"):
                                ui.label(a).classes("text-sm text-slate-600 p-2")
                    ui.separator().classes("my-5")
                    ui.label("Contact" if lang == "en" else "Contact").classes("text-lg font-black text-slate-900")
                    ui.label(support_email).classes("text-sm text-slate-600")
