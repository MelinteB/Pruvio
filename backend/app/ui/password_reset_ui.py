from nicegui import ui

from app.db.database import SessionLocal
from app.i18n import t
from app.services.account_service import confirm_password_reset, request_password_reset
from app.services.password_service import hash_password
from app.ui.app_shell import app_header, setup_page_head
from app.ui.auth_state import get_ui_language
from app.ui.email_otp_dialog import EmailOTPDialog
from app.ui.otp_recovery import OTPRecovery


def setup_password_reset_ui() -> None:
    @ui.page('/reset-password')
    def reset_password_page():
        lang = get_ui_language()
        setup_page_head(f"{t('Reset password', lang)} · Pruvs")
        state = {}
        with ui.element('main').classes('pruvio-page'), ui.column().classes('pruvio-shell gap-4'):
            app_header(t('Reset password', lang), show_account=False, language=lang)
            with ui.card().classes('pruvio-card w-full max-w-xl mx-auto p-6 sm:p-8'):
                ui.label(t('Reset password', lang)).classes('text-3xl font-black text-slate-950')
                ui.label('Confirmă noua parolă cu un cod trimis pe email.' if lang == 'ro' else 'Confirm your new password with a code sent to your email.').classes('text-sm text-slate-500')
                recovery = OTPRecovery('password-reset', lang)
                email = ui.input(t('Email address', lang)).props('outlined autocomplete=email').classes('w-full mt-3')
                password = ui.input(t('New password', lang), password=True, password_toggle_button=True).props('outlined autocomplete=new-password').classes('w-full')
                confirmation = ui.input(t('Confirm new password', lang), password=True, password_toggle_button=True).props('outlined autocomplete=new-password').classes('w-full')
                status = ui.label('').classes('text-xs text-red-600')

                def request_code(resend=False):
                    if not resend:
                        if password.value != confirmation.value:
                            raise ValueError('Parolele nu coincid.' if lang == 'ro' else 'Passwords do not match.')
                        hash_password(password.value or '')  # Validate before sending a code.
                        state['password'] = password.value
                        state['email'] = email.value or ''
                    db = SessionLocal()
                    try:
                        result = request_password_reset(db, state['email'])
                        state['email'] = result['destination']
                        state['challenge_id'] = result['challenge_id']
                        return result
                    finally:
                        db.close()

                def save(code):
                    if recovered_fields.visible:
                        if recovered_password.value != recovered_confirmation.value:
                            raise ValueError('Parolele nu coincid.' if lang == 'ro' else 'Passwords do not match.')
                        hash_password(recovered_password.value or '')
                        state['password'] = recovered_password.value or ''
                    db = SessionLocal()
                    try:
                        confirm_password_reset(db, state['email'], code, state['password'], challenge_id=state['challenge_id'])
                    finally:
                        db.close()
                    state.clear()
                    ui.notify('Parola a fost actualizată.' if lang == 'ro' else 'Password updated.', type='positive')
                    ui.navigate.to('/')

                popup = EmailOTPDialog(title='Confirmă resetarea' if lang == 'ro' else 'Confirm password reset',
                    description='Introdu codul pentru a salva noua parolă.' if lang == 'ro' else 'Enter the code to save your new password.',
                    on_verify=save, on_resend=lambda: request_code(True), language=lang, confirm_label=t('Save new password', lang))

                with popup.extra:
                    recovered_fields = ui.column().classes('w-full gap-3')
                    with recovered_fields:
                        ui.label('Reintrodu noua parolă; nu o salvăm în browser.' if lang == 'ro' else 'Re-enter your new password; it is not saved in browser storage.').classes('text-sm text-slate-500')
                        recovered_password = ui.input(t('New password', lang), password=True, password_toggle_button=True).props('outlined autocomplete=new-password').classes('w-full')
                        recovered_confirmation = ui.input(t('Confirm new password', lang), password=True, password_toggle_button=True).props('outlined autocomplete=new-password').classes('w-full')
                recovered_fields.visible = False
                recovery.field('email', email)
                def restore_reset():
                    state.pop('password', None)
                    recovered_fields.visible = True
                recovery.action('password-reset', popup, state, ('email', 'challenge_id'), restore_reset)
                recovery.start()

                def send():
                    status.set_text('')
                    try:
                        result = request_code()
                        recovered_fields.visible = False
                        recovered_password.set_value('')
                        recovered_confirmation.set_value('')
                        popup.present(result)
                    except Exception as error:
                        status.set_text(str(error))
                ui.button(t('Send reset code', lang), icon='mail_outline', on_click=send).classes('pruvio-primary w-full py-3')
                ui.label(t('Back to sign in', lang)).classes('pruvio-link text-sm self-center mt-2').on('click', lambda: ui.navigate.to('/'))
