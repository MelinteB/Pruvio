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
        setup_page_head(f"{t('Help', lang)} · Pruvs")
        support_email = os.getenv("PRUVIO_SUPPORT_EMAIL", "").strip()
        with ui.element("main").classes("pruvio-page"):
            with ui.column().classes("pruvio-shell gap-4"):
                app_header("Help & Support", show_account=False, language=lang)
                with ui.card().classes("pruvio-card w-full p-6 sm:p-8"):
                    ui.label(t("Help & Support", lang)).classes("text-3xl font-black text-slate-950")
                    ui.label("Întrebări frecvente pentru versiunea curentă Pruvs." if lang == "ro" else "Common questions for the current Pruvs test version.").classes("text-sm text-slate-500")
                    if lang == "ro":
                        faqs = [
                            ("Când este necesar codul OTP?", "Confirmi emailul la înregistrare. Resetarea parolei, schimbarea datelor de contact și ștergerea contului folosesc confirmare prin email. Autentificarea cu parolă sau passkey nu cere OTP pentru browser."),
                            ("Cum îmi resetez parola?", "Folosește opțiunea Ai uitat parola? și confirmă resetarea cu OTP trimis la emailul verificat."),
                            ("De ce poate greși OCR-ul?", "Extragerea și traducerea sunt automate. Verifică întotdeauna cantitățile, prețurile, moneda și totalul."),
                            ("Prietenii au nevoie de cont pentru split?", "Da. Participanții se autentifică sau creează un cont înainte să se alăture. Proprietarul gestionează nota din propriul cont."),
                            ("Pruvs procesează plăți?", "Nu în această etapă. Pruvs calculează și coordonează sumele; aplicația curentă nu procesează plăți."),
                            ("Cum îmi protejez contul?", "Nu divulga codurile OTP. Folosește passkey unde este posibil și deconectează-te de pe dispozitive partajate."),
                        ]
                    else:
                        faqs = [
                            ("When do I need an OTP?", "Verify your email at signup. Password recovery, contact changes and account deletion use email confirmation. Password and passkey sign-in do not require a browser OTP."),
                            ("How do I reset my password?", "Use Forgot password and confirm the reset with an OTP sent to your verified email."),
                            ("Why can OCR be wrong?", "Receipt extraction and translation are automated. Always review quantities, prices, currency and totals before splitting a bill."),
                            ("Do friends need accounts to join a split?", "Yes. Participants sign in or create an account before joining. The bill owner manages the bill from their own account."),
                            ("Does Pruvs move money?", "Not in this stage. Pruvs calculates and coordinates amounts; payments are not processed by the current app."),
                            ("How do I protect my account?", "Never share OTP codes. Use a passkey where possible and sign out on shared devices."),
                        ]
                    with ui.column().classes("gap-4 mt-4"):
                        for q, a in faqs:
                            with ui.expansion(q).classes("w-full border border-slate-200 rounded-xl"):
                                ui.label(a).classes("text-sm text-slate-600 p-2")
                    ui.separator().classes("my-5")
                    ui.label("Contact" if lang == "en" else "Contact").classes("text-lg font-black text-slate-900")
                    ui.label(support_email or ("Adresa de suport nu este încă disponibilă." if lang == "ro" else "The support email is not available yet.")).classes("text-sm text-slate-600")
