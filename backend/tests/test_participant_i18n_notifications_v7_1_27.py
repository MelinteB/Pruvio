"""v7.1.28: notification delivery behavior and privacy, plus interface contracts."""
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import importlib, pkgutil
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models import __path__ as model_paths
for module in pkgutil.iter_modules(model_paths):
    importlib.import_module('app.models.' + module.name)
from app.models.push_notification import PushEvent, PushDevice, PushDelivery, PushGrant
from app.models.user import User
from app.react_app import push_worker
from app.api import push_notifications
from app.reliability import RELEASE

ROOT = Path(__file__).resolve().parents[1]


class NotificationReliabilityTests(unittest.TestCase):
    def test_release_and_source_alignment(self):
        self.assertEqual(RELEASE, '7.1.28')
        self.assertIn("version:'7.1.28'", (ROOT / 'frontend/scripts/stamp-build.mjs').read_text())
        self.assertIn('pruvs-shell-v7.1.28', (ROOT / 'app/static/react-service-worker.js').read_text())
        self.assertIn("CLIENT_RELEASE = '7.1.28'", (ROOT / 'frontend/src/professional/ReleaseUpdateBanner.jsx').read_text())

    def test_transient_and_permanent_provider_failures(self):
        for code in (0, 408, 429, 500, 502, 503):
            self.assertEqual(push_worker.push_failure(code, 1), (False, 30))
        for code in (400, 401, 403, 404, 410, 413, 301):
            self.assertEqual(push_worker.push_failure(code, 1), (True, None))

    def test_retry_is_bounded_with_backoff(self):
        self.assertEqual(push_worker.push_failure(503, 2), (False, 60))
        self.assertEqual(push_worker.push_failure(503, 3), (False, 120))
        self.assertEqual(push_worker.push_failure(503, 4), (False, 240))
        self.assertEqual(push_worker.push_failure(503, 5), (True, None))
        self.assertLessEqual(push_worker.MAX_PUSH_ATTEMPTS, 5)

    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        now = datetime.utcnow()
        self.db.add_all([
            User(id=11, username='alpha', username_key='alpha', phone_number='+40000000011', name='Alpha', status='active', notifications_opt_in=True),
            User(id=12, username='beta', username_key='beta', phone_number='+40000000012', name='Beta', status='active', notifications_opt_in=True),
            PushGrant(token_hash='a'*64, user_id=11, active=True, expires_at=now+timedelta(days=2)),
            PushDevice(id='device-11', user_id=11, grant_hash='a'*64, endpoint_hash='b'*64, subscription='{}', label='Test', active=True, confirmed_at=now),
            PushEvent(id='event-11', user_id=11, kind='payment_marked', title='Payment reported', body='Test', url='/bill/example', status='pending', available_at=now, expires_at=now+timedelta(days=1), created_at=now),
            PushEvent(id='event-12', user_id=12, kind='payment_received', title='Private message', body='Other user', url='/bill/private', status='pending', available_at=now, expires_at=now+timedelta(days=1), created_at=now),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def pref(self):
        return SimpleNamespace(push_enabled=True, email_enabled=False, receipts=True, bills=True, reminders=True)

    def test_transient_failure_then_retry_then_provider_acceptance(self):
        event=self.db.get(PushEvent, 'event-11')
        with patch.object(push_worker, 'enabled', return_value=True), patch.object(push_worker, 'preferences', return_value=self.pref()), patch.object(push_worker, 'send_push', side_effect=[503, 201]) as push:
            push_worker.deliver(self.db,event)
            self.assertEqual(event.status,'pending')
            delivery=self.db.get(PushDelivery,'event-11:device-11')
            self.assertEqual(delivery.attempts,1)
            self.assertEqual(delivery.status,'pending')
            self.assertTrue(event.available_at>datetime.utcnow())
            push_worker.deliver(self.db,event)
            self.assertEqual(event.status,'accepted')
            self.assertEqual(delivery.attempts,2)
            self.assertEqual(delivery.status,'accepted')
            self.assertEqual(push.call_count,2)

    def test_gone_device_is_deactivated_without_retry_storm(self):
        event=self.db.get(PushEvent,'event-11')
        with patch.object(push_worker,'enabled',return_value=True), patch.object(push_worker,'preferences',return_value=self.pref()), patch.object(push_worker,'send_push',return_value=410):
            push_worker.deliver(self.db,event)
        self.assertEqual(event.status,'in_app_only')
        self.assertFalse(self.db.get(PushDevice,'device-11').active)
        self.assertEqual(self.db.get(PushDelivery,'event-11:device-11').status,'failed')

    def test_diagnostic_state_is_scoped_to_signed_in_account(self):
        # Another user's push messages must never appear in the caller's diagnostics.
        self.db.add(PushDelivery(id='event-11:device-11',event_id='event-11',device_id='device-11',status='failed',attempts=1,error_code='http_503'))
        self.db.add(PushDelivery(id='event-12:other',event_id='event-12',device_id='other',status='accepted',attempts=1))
        self.db.commit()
        with patch.object(push_notifications.service,'preferences',return_value=self.pref()),patch.object(push_notifications.service,'enabled',return_value=True):
            value=push_notifications.state(Response(), grant=SimpleNamespace(user_id=11,token_hash='a'*64),db=self.db)
        self.assertEqual([e['id'] for e in value['events']],['event-11'])
        self.assertEqual(value['events'][0]['delivery']['failed'],1)
        self.assertNotIn('endpoint',str(value))
        self.assertNotIn('Private message',str(value))

    def test_worker_flag_is_not_mistaken_for_provider_receipt(self):
        with patch.object(push_notifications.service,'preferences',return_value=self.pref()),patch.object(push_notifications.service,'enabled',return_value=True),patch.dict(os.environ,{'PRUVS_PUSH_WORKER_ENABLED':'false'}):
            value=push_notifications.state(Response(), grant=SimpleNamespace(user_id=11,token_hash='a'*64),db=self.db)
        self.assertFalse(value['worker_enabled'])
        self.assertEqual(value['events'][0]['status'],'pending')

    def test_color_and_translations_are_not_tied_to_payment_state(self):
        colors=(ROOT/'frontend/src/participant-colors.js').read_text()
        self.assertIn('itemShareGradient',colors)
        self.assertIn('participantColors',colors)
        self.assertNotIn('payment_status',colors)
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        self.assertIn('itemShareGradient(item, colors)',bill)
        self.assertIn('participantStyle(colors, a.participant_id)',bill)
        self.assertIn('is-fully-allocated',bill)
        translations=(ROOT/'frontend/src/i18n.js').read_text()
        for label in ('Confirm received','Payment history','SHARED BILL OVERVIEW','Invite more people','Selected by you'):
            self.assertIn(label, translations)

if __name__ == '__main__':
    unittest.main()
