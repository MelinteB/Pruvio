"""A single, on-demand email verification dialog for account actions."""
import inspect
import re

from nicegui import ui
from app.services.phone_otp_service import delivery_message
from app.ui.app_shell import logo_mark


def mask_email(value: str) -> str:
    local, _, domain = (value or '').partition('@')
    return f'{local[:2]}***@{domain}' if domain else value


class EmailOTPDialog:
    def __init__(self, *, title: str, description: str, on_verify, on_resend,
                 language: str = 'en', confirm_label: str | None = None, danger: bool = False):
        self.language = language
        self.on_verify = on_verify
        self.on_resend = on_resend
        self.busy = False
        self.recovery = None
        self.recovery_action = None
        self.destination = ''
        ro = language == 'ro'
        ui.add_css('.pruvio-otp-code input { text-align: center; font-size: 24px; letter-spacing: .32em; font-weight: 600; }')
        self.dialog = ui.dialog().props('persistent')
        with self.dialog, ui.card().classes('w-full max-w-md p-6 sm:p-8 rounded-3xl gap-4 pruvs-otp-card').style('max-width: min(440px, calc(100vw - 32px))'):
            with ui.row().classes('w-full items-center justify-between'):
                logo_mark(48)
                self.close_button = ui.button(icon='close', on_click=self.close).props('flat round aria-label=Close')
            ui.label(title).classes('text-2xl font-black text-slate-950')
            ui.label(description).classes('text-sm text-slate-500 leading-relaxed')
            self.recipient = ui.label('').classes('text-sm font-bold text-slate-800')
            self.action_detail = ui.label('').classes('text-sm text-slate-700')
            self.action_detail.visible = False
            self.extra = ui.column().classes('w-full gap-3')
            self.code = ui.input('Cod de verificare' if ro else 'Verification code').props(
                'outlined inputmode=numeric maxlength=6 autocomplete=one-time-code autofocus'
            ).classes('w-full pruvio-otp-code')
            self.error = ui.label('').classes('text-sm text-red-600').props('role=alert')
            self.debug = ui.label('').classes('text-xs text-amber-700')
            self.debug.visible = False
            self.confirm_button = ui.button(confirm_label or ('Confirmă' if ro else 'Confirm'), icon='verified_user', on_click=self.verify).classes(
                'w-full py-3 rounded-xl font-bold ' + ('bg-red-700 text-white' if danger else 'pruvio-primary')
            )
            with ui.row().classes('w-full justify-between items-center'):
                self.resend_button = ui.button('Retrimite codul' if ro else 'Resend code', on_click=self.resend).props('flat no-caps').classes('text-slate-600')
                self.cancel_button = ui.button('Anulează' if ro else 'Cancel', on_click=self.close).props('flat no-caps').classes('text-slate-500')
            self.code.on('keydown.enter', self.verify)

    def close(self):
        if not self.busy:
            self.code.set_value('')
            self.dialog.close()
            if self.recovery:
                self.recovery.clear()

    def present(self, result: dict, *, recovering: bool = False) -> bool:
        delivery = result.get('delivery') or {}
        if not delivery.get('sent') and not result.get('debug_otp'):
            raise ValueError(delivery_message(delivery, result.get('destination', self.destination), self.language))
        self.destination = result.get('destination') or self.destination
        self.recipient.set_text(('Cod trimis la ' if self.language == 'ro' else 'Code sent to ') + mask_email(self.destination))
        proposed_phone = result.get('requested_value') if result.get('contact_type') == 'phone' else None
        self.action_detail.set_text(('Telefon nou: ' if self.language == 'ro' else 'New phone number: ') + proposed_phone if proposed_phone else '')
        self.action_detail.visible = bool(proposed_phone)
        self.code.set_value('')
        self.error.set_text('')
        self.debug.set_text(f"Local debug OTP: {result['debug_otp']}" if result.get('debug_otp') else '')
        self.debug.visible = bool(result.get('debug_otp'))
        if self.recovery and not recovering:
            self.recovery.save(self.recovery_action, result)
        self.dialog.open()
        return True

    def _busy(self, value: bool):
        self.busy = value
        for button in (self.confirm_button, self.resend_button, self.cancel_button, self.close_button):
            button.disable() if value else button.enable()
        self.code.disable() if value else self.code.enable()

    async def verify(self):
        if self.busy or not self.dialog.value:
            return
        code = (self.code.value or '').strip()
        if not re.fullmatch(r'[0-9]{6}', code):
            self.error.set_text('Introdu codul de 6 cifre.' if self.language == 'ro' else 'Enter the 6-digit code.')
            return
        self._busy(True)
        self.error.set_text('')
        try:
            result = self.on_verify(code)
            if inspect.isawaitable(result):
                await result
            if self.recovery:
                self.recovery.clear(clear_fields=True)
            self.code.set_value('')
            self.dialog.close()
        except Exception as error:
            self.error.set_text(str(error) or ('Verificarea a eșuat.' if self.language == 'ro' else 'Verification failed.'))
        finally:
            self._busy(False)

    async def resend(self):
        if self.busy:
            return
        self._busy(True)
        try:
            result = self.on_resend()
            if inspect.isawaitable(result):
                result = await result
            self.present(result)
        except Exception as error:
            self.error.set_text(str(error))
        finally:
            self._busy(False)
