"""Database outbox. Run one worker process (or enable the embedded worker).
Provider acceptance is NOT proof of display. Delivery is at least once.
"""
import asyncio
import json
import logging
import os
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import or_, and_
from app.db.database import SessionLocal
from app.models.push_notification import PushEvent, PushDevice, PushDelivery, PushGrant
from app.services.push_service import active_user, preferences, enabled, validate_subscription

log = logging.getLogger(__name__)


def send_push(device, payload):
    from pywebpush import webpush
    # Deny redirects: a subscription may never redirect into the local network.
    import requests
    class NoRedirects(requests.Session):
        def request(self, *args, **kwargs):
            kwargs['allow_redirects'] = False
            return super().request(*args, **kwargs)
    with NoRedirects() as session:
        response = webpush(subscription_info=validate_subscription(json.loads(device.subscription)),
                           data=json.dumps(payload), vapid_private_key=os.environ['PRUVS_VAPID_PRIVATE_KEY'],
                           vapid_claims={'sub': os.environ['PRUVS_VAPID_SUBJECT']},
                           ttl=900, timeout=10, requests_session=session)
    return response.status_code


def send_email(user, event):
    base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if not base.startswith('https://'):
        return False
    text = f'{event.title}\n\n{event.body}\n\nOpen Pruvs: {base}/notifications/open/{event.id}'
    if os.getenv('EMAIL_PROVIDER', 'smtp').lower() == 'resend':
        key, sender = os.getenv('RESEND_API_KEY'), os.getenv('EMAIL_FROM')
        if not key or not sender:
            return False
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            r = client.post('https://api.resend.com/emails', headers={
                'Authorization': f'Bearer {key}', 'Idempotency-Key': f'pruvs-notification-{event.id}'},
                json={'from': sender, 'to': [user.email], 'subject': event.title, 'text': text})
            return r.is_success
    host, sender = os.getenv('SMTP_HOST'), os.getenv('SMTP_FROM_EMAIL')
    if not host or not sender:
        return False
    message = EmailMessage()
    message['Subject'], message['From'], message['To'] = event.title, sender, user.email
    message['Message-ID'] = f'<pruvs-{event.id}@pruvs.io>'
    message.set_content(text)
    use_ssl = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
    cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with cls(host, int(os.getenv('SMTP_PORT', '587')), timeout=15) as server:
        if not use_ssl and os.getenv('SMTP_USE_TLS', 'true').lower() == 'true':
            server.starttls(context=ssl.create_default_context())
        if os.getenv('SMTP_USERNAME'):
            server.login(os.environ['SMTP_USERNAME'], os.getenv('SMTP_PASSWORD', ''))
        server.send_message(message)
    return True


def claim(db):
    now = datetime.utcnow()
    due = or_(and_(PushEvent.status == 'pending', PushEvent.available_at <= now),
              and_(PushEvent.status == 'processing', PushEvent.lease_until < now))
    for (eid,) in db.query(PushEvent.id).filter(due).order_by(PushEvent.available_at).limit(20):
        token = str(uuid.uuid4())
        count = db.query(PushEvent).filter(PushEvent.id == eid, due).update({
            'status': 'processing', 'lease_until': now + timedelta(minutes=10), 'lease_token': token}, synchronize_session=False)
        db.commit()
        if count:
            return db.get(PushEvent, eid)
    return None


def deliver(db, event):
    user = active_user(db, event.user_id)
    if not user:
        event.status = 'cancelled'; db.commit(); return
    pref = preferences(db, user.id)
    category = 'receipts' if event.kind.startswith('receipt') else ('reminders' if event.kind == 'reminder' else 'bills')
    if event.kind != 'test' and (not user.notifications_opt_in or not getattr(pref, category)):
        event.status = 'muted'; db.commit(); return
    # Old jobs must not emit obsolete payment reminders after a long outage.
    if datetime.utcnow() > event.expires_at:
        event.status = 'expired'; db.commit(); return
    if event.kind == 'test' and datetime.utcnow() - event.created_at > timedelta(minutes=15):
        event.status = 'expired'; db.commit(); return
    devices = []
    if enabled() and (pref.push_enabled or event.kind == 'test'):
        devices = db.query(PushDevice).filter_by(user_id=user.id, active=True).all()
    if event.device_id:
        devices = [d for d in devices if d.id == event.device_id]
    retry = False
    for device in devices:
        db.refresh(device)
        grant = db.get(PushGrant, device.grant_hash, populate_existing=True)
        if not device.active or not grant or not grant.active or grant.expires_at <= datetime.utcnow():
            continue
        if event.kind != 'test' and not device.confirmed_at:
            continue
        key = f'{event.id}:{device.id}'
        delivery = db.get(PushDelivery, key)
        if delivery is None:
            delivery = PushDelivery(id=key, event_id=event.id, device_id=device.id)
            db.add(delivery); db.flush()
        if delivery.status in ('accepted', 'failed'):
            continue
        delivery.attempts += 1
        db.commit()
        # No bill content or user identity is exposed on a shared lock screen.
        payload = {'title': 'Pruvs', 'body': 'You have an update in Pruvs. Tap to view.',
                   'tag': event.id, 'url': f'/notifications/open/{event.id}'}
        if event.kind == 'test':
            payload.update(title=event.title, body=event.body,
                           url=f'/notifications#confirm={event.confirmation}')
        try:
            code = send_push(device, payload)
        except Exception as exc:
            response = getattr(exc, 'response', None)
            code = getattr(response, 'status_code', None) or 0
        if 200 <= code < 300:
            delivery.status = 'accepted'; delivery.error_code = None
        else:
            delivery.error_code = f'http_{code}' if code else 'transport_error'
            permanent = code in (400, 401, 403, 404, 410, 413) or 300 <= code < 400
            if code in (404, 410):
                device.active = False
            delivery.status = 'failed' if permanent or delivery.attempts >= 3 else 'pending'
            retry = retry or delivery.status == 'pending'
        db.commit()
    accepted = db.query(PushDelivery).filter_by(event_id=event.id, status='accepted').count() > 0
    if retry:
        event.status = 'pending'; event.available_at = datetime.utcnow() + timedelta(seconds=60)
    elif accepted:
        event.status = 'accepted'
    elif event.kind != 'test' and pref.email_enabled and user.email and user.is_email_verified:
        if event.email_status != 'accepted' and event.email_attempts < 3:
            event.email_attempts += 1
            db.commit()
            try:
                ok = send_email(user, event)
            except Exception:
                ok = False
            event.email_status = 'accepted' if ok else 'failed'
        if event.email_status == 'accepted':
            event.status = 'email_accepted'
        elif event.email_attempts < 3:
            event.status = 'pending'; event.available_at = datetime.utcnow() + timedelta(seconds=120)
        else:
            event.status = 'failed'
    else:
        event.status = 'in_app_only' if event.kind != 'test' else 'failed'
    event.lease_until = None
    db.commit()


def run_once():
    with SessionLocal() as db:
        event = claim(db)
        if event is None:
            return False
        deliver(db, event)
        return True


async def loop(stop):
    while not stop.is_set():
        try:
            worked = await asyncio.to_thread(run_once)
        except Exception:
            log.exception('Notification queue processing failed')
            worked = False
        if not worked:
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass


def install_worker(app):
    # NiceGUI owns the ASGI lifespan; its startup/shutdown hooks are used here.
    from nicegui import app as nicegui_app
    state = {}
    async def start():
        if os.getenv('PRUVS_PUSH_WORKER_ENABLED', 'false').lower() == 'true':
            state['stop'] = asyncio.Event()
            state['task'] = asyncio.create_task(loop(state['stop']))
    async def stop():
        if state.get('task'):
            state['stop'].set()
            await state['task']
    nicegui_app.on_startup(start)
    nicegui_app.on_shutdown(stop)
