import json
from datetime import datetime
from nicegui import app as nicegui_app, ui
from app.db.database import SessionLocal
from app.models.push_notification import PushEvent
from app.services.push_service import create_grant, grant_for, revoke_grant, active_user
from app.ui.auth_state import require_login, get_logged_in_user_id
from app.ui.app_shell import setup_page_head, app_header, bottom_nav


def browser_grant():
    uid = get_logged_in_user_id()
    token = nicegui_app.storage.user.get('push_grant')
    with SessionLocal() as db:
        existing = grant_for(db, token)
        if existing and existing.user_id == uid:
            return token
    revoke_grant(token)
    token = create_grant(uid)
    nicegui_app.storage.user['push_grant'] = token
    return token


def setup_notifications_ui():
    @ui.page('/notifications')
    def notifications_page():
        uid = require_login('/notifications')
        if uid is None:
            return
        setup_page_head('Notifications · Pruvs')
        try:
            token = browser_grant()
        except ValueError:
            ui.label('Sign in with an active account to enable notifications.'); return
        with ui.element('main').classes('pruvio-page'):
            with ui.column().classes('pruvio-shell gap-4'):
                app_header('Notifications')
                ui.html('''<section class="pruvio-card" style="padding:24px;width:100%" id="pruvs-notifications">
<h1 style="font-size:26px;font-weight:800">Notifications on this device</h1>
<p>Receive receipt updates, bill changes and payment reminders even when Pruvs is closed.</p>
<p id="push-status" role="status" aria-live="polite">Checking this device…</p>
<div id="push-help" style="margin:16px 0"></div>
<div style="display:flex;gap:10px;flex-wrap:wrap">
<button id="push-enable" class="pruvio-primary" style="padding:10px 16px" disabled>Enable notifications on this device</button>
<button id="push-test" class="pruvio-secondary" style="padding:10px 16px" disabled>Send test notification</button>
<button id="push-disable" class="pruvio-secondary" style="padding:10px 16px" disabled>Disable on this device</button>
</div>
<p style="margin-top:14px">After sending a test, return to your Home Screen or lock your phone. Tap the Pruvs notification to confirm receipt.</p>
<h2 style="font-size:20px;font-weight:700;margin-top:24px">Notification preferences</h2>
<p>Business alerts also follow your Account → Product notifications preference.</p>
<div id="push-preferences"></div>
<button id="push-save" class="pruvio-secondary" style="padding:8px 16px;margin-top:10px" disabled>Save preferences</button>
<h2 style="font-size:20px;font-weight:700;margin-top:24px">Your devices</h2><div id="push-devices"></div>
<h2 style="font-size:20px;font-weight:700;margin-top:24px">Recent notifications</h2><div id="push-history"></div>
</section>''', sanitize=False)
                target = nicegui_app.storage.user.get('push_next', '/')
                if not isinstance(target, str) or not target.startswith('/') or target.startswith('//') or '\\' in target:
                    target = '/'
                ui.button('Continue to Pruvs', on_click=lambda: ui.navigate.to(target)).classes('pruvio-primary')
                ui.label('You can skip device setup and use email fallback. Change these choices here at any time.').classes('text-sm text-slate-500')
        bottom_nav('account')
        ui.add_head_html('<script src="/static/pruvs-push.js?v=6.12.2"></script>')
        async def initialise():
            await ui.run_javascript('return window.PruvsPush.init(' + json.dumps({'token': token, 'account': str(uid)}) + ')', timeout=20)
        ui.timer(0.2, initialise, once=True)

    @ui.page('/notifications/open/{event_id}')
    def open_notification(event_id: str):
        uid = require_login(f'/notifications/open/{event_id}')
        if uid is None:
            return
        with SessionLocal() as db:
            if not active_user(db, uid):
                ui.label("Sign in with an active account to view this notification."); return
            event = db.get(PushEvent, event_id)
            if not event or event.user_id != uid:
                ui.label('This notification is unavailable for this account.'); return
            target = event.url
            if event.kind == 'test':
                target = '/notifications'
            elif target.startswith('/receipt/'):
                from app.models.case import Case
                case = db.get(Case, int(target.rsplit('/', 1)[1]))
                if not case or case.user_id != uid:
                    ui.label('This receipt is no longer available.'); return
            elif target.startswith('/split-bill/sessions/'):
                from app.models.split_bill_session import SplitBillSession
                from app.models.split_bill_participant import SplitBillParticipant
                session = db.query(SplitBillSession).filter_by(token=target.split('/')[3]).first()
                participant = db.query(SplitBillParticipant).filter_by(session_id=session.id, user_id=uid).first() if session else None
                if not participant or participant.status != 'joined':
                    ui.label('You no longer have access to this bill.'); return
                if session.owner_user_id == uid:
                    target = f'/split-bill/sessions/{session.token}/widget-ui?participant_id={participant.id}'
                else:
                    target = f'/split-bill/sessions/{session.token}/p/{participant.participant_token}/widget-ui'
            if not target.startswith('/') or target.startswith('//') or '\\' in target:
                target = '/history'
            event.read_at = datetime.utcnow()
            db.commit()
        ui.navigate.to(target)
