"""User-scoped push registration and durable event creation."""
import base64
import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from app.db.database import SessionLocal
from app.models.user import User
from app.models.push_notification import PushGrant, PushDevice, PushPreference, PushEvent


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def configured():
    return bool(os.getenv('PRUVS_VAPID_PUBLIC_KEY') and os.getenv('PRUVS_VAPID_PRIVATE_KEY')
                and os.getenv('PRUVS_VAPID_SUBJECT'))


def enabled():
    return os.getenv('PRUVS_PUSH_ENABLED', 'false').lower() == 'true' and configured()


def active_user(db, user_id):
    user = db.get(User, user_id)
    return user if user and user.status == 'active' else None


def grant_for(db, token):
    if not token or len(token) > 200:
        return None
    grant = db.get(PushGrant, digest(token))
    if not grant or not grant.active or grant.expires_at <= datetime.utcnow():
        return None
    return grant if active_user(db, grant.user_id) else None


def create_grant(user_id):
    token = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        if not active_user(db, user_id):
            raise ValueError('Sign in with an active account.')
        db.add(PushGrant(token_hash=digest(token), user_id=user_id,
                         expires_at=datetime.utcnow() + timedelta(days=30)))
        db.commit()
    return token


def revoke_grant(token):
    if not token:
        return
    with SessionLocal() as db:
        key = digest(token)
        db.query(PushGrant).filter_by(token_hash=key).update({'active': False})
        db.query(PushDevice).filter_by(grant_hash=key).update({'active': False, 'test_hash': None})
        db.commit()


def preferences(db, user_id):
    row = db.get(PushPreference, user_id)
    if row is None:
        row = PushPreference(user_id=user_id)
        db.add(row)
        db.flush()
    return row


def validate_subscription(value):
    """Only send to recognized push services, never arbitrary submitted URLs."""
    if not isinstance(value, dict):
        raise ValueError('Invalid push subscription.')
    endpoint = value.get('endpoint', '')
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        raise ValueError('Invalid push endpoint.')
    url = urlsplit(endpoint)
    host = (url.hostname or '').lower()
    allowed = host == 'fcm.googleapis.com' or host == 'updates.push.services.mozilla.com' or host == 'web.push.apple.com' or host.endswith('.push.apple.com') or host.endswith('.notify.windows.com')
    if (not allowed or url.scheme != 'https' or url.port not in (None, 443)
            or url.username or url.password or url.fragment):
        raise ValueError('Unsupported push service. Use Safari, Chrome, Edge or Firefox.')
    keys = value.get('keys', {})
    clean = {}
    for key, expected in [('auth', 16), ('p256dh', 65)]:
        raw = keys.get(key, '')
        if not isinstance(raw, str) or len(raw) > 160:
            raise ValueError('Invalid subscription keys.')
        try:
            decoded = base64.b64decode(raw + '=' * (-len(raw) % 4), altchars=b'-_', validate=True)
        except Exception as exc:
            raise ValueError('Invalid subscription keys.') from exc
        if len(decoded) != expected or (key == 'p256dh' and decoded[0] != 4):
            raise ValueError('Invalid subscription keys.')
        clean[key] = raw
    return {'endpoint': endpoint, 'keys': clean}


def register_device(db, grant, subscription, label):
    subscription = validate_subscription(subscription)
    key = digest(subscription['endpoint'])
    row = db.query(PushDevice).filter_by(endpoint_hash=key).first()
    if row and row.user_id != grant.user_id:
        raise ValueError('This subscription belongs to another account. Disable and enable notifications on this device.')
    if row is None:
        if db.query(PushDevice).filter_by(user_id=grant.user_id, active=True).count() >= 10:
            raise ValueError('Maximum 10 devices. Disable an old device first.')
        row = PushDevice(id=str(uuid.uuid4()), user_id=grant.user_id,
                         endpoint_hash=key, subscription=json.dumps(subscription), label=label[:120])
        db.add(row)
    if row.grant_hash != grant.token_hash or not row.active:
        row.confirmed_at = None
        row.test_hash = None
    row.grant_hash = grant.token_hash
    row.subscription = json.dumps(subscription)
    row.label = label[:120]
    row.active = True
    row.updated_at = datetime.utcnow()
    # PRUVS_6122_DEVICE_OPT_IN: enabling browser push is explicit user consent.
    # This allows a user who initially unchecked signup consent to opt in later.
    user = db.get(User, grant.user_id)
    if user is None or user.status != 'active':
        raise ValueError('Sign in with an active account.')
    user.notifications_opt_in = True
    db.commit()
    return row


def enqueue(db, user_id, kind, title, body, url='/history', *, device_id=None, confirmation=None, when=None):
    if not url.startswith('/') or url.startswith('//') or '\\' in url:
        raise ValueError('Notification link must be a local path.')
    event = PushEvent(id=str(uuid.uuid4()), user_id=user_id, kind=kind,
                      title=title[:120], body=body[:500], url=url[:500],
                      device_id=device_id, confirmation=confirmation,
                      available_at=when or datetime.utcnow(),
                      expires_at=(when or datetime.utcnow()) + timedelta(days=1))
    db.add(event)
    db.flush()
    return event


def test_device(db, grant, device_id):
    device = db.get(PushDevice, device_id)
    if not device or device.user_id != grant.user_id or device.grant_hash != grant.token_hash or not device.active:
        raise ValueError('Enable notifications on this device first.')
    now = datetime.utcnow()
    if device.last_test_at and now - device.last_test_at < timedelta(seconds=30):
        raise ValueError('Wait 30 seconds before sending another test.')
    code = secrets.token_urlsafe(32)
    device.test_hash = digest(code)
    device.test_expires_at = now + timedelta(minutes=15)
    device.last_test_at = now
    event = enqueue(db, grant.user_id, 'test', 'Pruvs notifications are ready',
                    'Tap this notification to confirm receipt on this device.', '/notifications',
                    device_id=device.id, confirmation=code)
    db.commit()
    return event


def confirm_test(db, grant, code):
    device = db.query(PushDevice).filter_by(user_id=grant.user_id, grant_hash=grant.token_hash,
                                           test_hash=digest(code), active=True).first()
    if not device or not device.test_expires_at or device.test_expires_at < datetime.utcnow():
        raise ValueError('Test expired or belongs to a different login. Send a new test.')
    device.confirmed_at = datetime.utcnow()
    device.test_hash = None
    db.commit()
    return device


def bill_event(db, session, kind, title, body):
    from app.models.split_bill_participant import SplitBillParticipant
    recipients = {session.owner_user_id}
    recipients.update(p.user_id for p in db.query(SplitBillParticipant).filter_by(session_id=session.id, status='joined') if p.user_id)
    for user_id in recipients:
        enqueue(db, user_id, kind, title, body, f'/split-bill/sessions/{session.token}/join')
