"""v7.1.33 real SQLite privacy checks: authenticated user's data only."""
import importlib
import pkgutil
import unittest
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.db.database import Base
from app.models import __path__ as model_paths
for module in pkgutil.iter_modules(model_paths):
    importlib.import_module('app.models.' + module.name)
from app.models.user import User
from app.models.case import Case
from app.models.receipt_item import ReceiptItem
from app.models.document import Document
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.payment_confirmation_event import PaymentConfirmationEvent
from app.react_app.data_export import snapshot, iso
from app.reliability import RELEASE
from scripts.privacy_readiness import audit

ROOT = Path(__file__).resolve().parents[1]


class PrivacyExportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.db.add_all([
            User(id=11, phone_number='+400011', username='mine', username_key='mine', email='mine@example.com',
                 password_hash='PRIVATE_PASSWORD_HASH', payment_iban='MY_IBAN', status='active'),
            User(id=12, phone_number='+400012', username='other', username_key='other', email='other@example.com',
                 password_hash='OTHER_PASSWORD_HASH', payment_iban='OTHER_IBAN', status='active'),
            Case(id=100, user_id=11, status='processed', module='receipt'),
            Case(id=200, user_id=12, status='processed', module='receipt'),
            Document(id=500, case_id=100, stored_filename='owned.jpg', path='owned.jpg'),
            Document(id=600, case_id=200, stored_filename='other.jpg', path='other.jpg'),
            ReceiptItem(id=300, case_id=100, document_id=500, name='My pasta', quantity=2, total_price=20, currency='RON'),
            ReceiptItem(id=400, case_id=200, document_id=600, name='Secret product', quantity=3, total_price=30, currency='RON'),
            SplitBillSession(id=10, case_id=200, owner_user_id=12, token='PRIVATE_INVITE_TOKEN', status='settled'),
            SplitBillSession(id=20, case_id=200, owner_user_id=12, token='ANOTHER_PRIVATE_TOKEN', status='settled'),
            SplitBillParticipant(id=51, session_id=10, user_id=11, display_name='Mine', participant_token='PT_MINE',
                                 payment_status='received', role='participant'),
            SplitBillParticipant(id=52, session_id=10, user_id=12, display_name='Other secret name',
                                 participant_token='PT_OTHER', payment_status='unpaid', role='owner'),
            SplitBillParticipant(id=53, session_id=20, user_id=12, display_name='Other again',
                                 participant_token='PT_OTHER_2', payment_status='paid', role='owner'),
            PaymentConfirmationEvent(id=1, session_id=10, participant_id=51, actor_user_id=12,
                                     event_type='received', amount=Decimal('10.00'), currency='RON'),
            PaymentConfirmationEvent(id=2, session_id=10, participant_id=52, actor_user_id=12,
                                     event_type='reported', amount=Decimal('77.00'), currency='RON'),
            PaymentConfirmationEvent(id=3, session_id=20, participant_id=53, actor_user_id=12,
                                     event_type='reported', amount=Decimal('88.00'), currency='RON'),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_user_scoped_export_and_no_secret_leak(self):
        import json
        me = self.db.get(User, 11)
        data = snapshot(self.db, me)
        self.assertEqual(data['format'], 'pruvs-account-activity-v1')
        self.assertEqual([c['case_id'] for c in data['owned_scans']], [100])
        self.assertEqual([i['name'] for i in data['owned_receipt_items']], ['My pasta'])
        self.assertEqual([b['bill_id'] for b in data['my_bill_participation']], [10])
        self.assertEqual([e['event_id'] for e in data['my_payment_history']], [1])
        self.assertEqual(data['my_payment_history'][0]['actor_role'], 'bill_owner_or_other')
        rendered = json.dumps(data)
        for forbidden in ('PRIVATE_PASSWORD_HASH', 'OTHER_PASSWORD_HASH', 'other@example.com',
                          'OTHER_IBAN', 'PRIVATE_INVITE_TOKEN', 'ANOTHER_PRIVATE_TOKEN',
                          'PT_MINE', 'PT_OTHER', 'Secret product', 'Other secret name',
                          '77.00', '88.00'):
            self.assertNotIn(forbidden, rendered)
        self.assertIn('MY_IBAN', rendered)  # The user's own saved details may be included.
        self.assertEqual(iso(datetime(2026, 1, 2)), '2026-01-02T00:00:00Z')

    def test_export_does_not_mutate_database(self):
        before = self.db.query(PaymentConfirmationEvent).count()
        snapshot(self.db, self.db.get(User, 11))
        self.assertEqual(self.db.query(PaymentConfirmationEvent).count(), before)

    def test_cannot_silently_truncate(self):
        with patch('app.react_app.data_export.MAX_EXPORT_ROWS', 0):
            with self.assertRaises(HTTPException) as exc:
                snapshot(self.db, self.db.get(User, 11))
        self.assertEqual(exc.exception.status_code, 413)

    def test_release_and_translated_ui(self):
        self.assertEqual(RELEASE, '7.1.33')
        ui = (ROOT / 'frontend/src/Account.jsx').read_text()
        self.assertIn("send('/account/data-export')", ui)
        self.assertIn('URL.revokeObjectURL', ui)
        self.assertIn('Download my activity', (ROOT / 'frontend/src/i18n.js').read_text())
        api = (ROOT / 'app/react_app/api.py').read_text()
        self.assertIn("@router.post('/account/data-export')", api)
        self.assertIn('identity=Depends(current)', api)
        self.assertIn('private, no-store', api)

    def test_privacy_audit_never_displays_secrets_and_flags_placeholder(self):
        config = {'DATABASE_URL': 'postgresql://top-secret-password@db/production',
                  'PUBLIC_BASE_URL': 'https://super-private-subdomain.pruvs.io',
                  'PRUVS_REQUIRE_POSTGRES': 'true'}
        rows = audit(ROOT, config)
        string = str(rows)
        self.assertIn('BLOCKER', string)
        self.assertNotIn('top-secret', string)
        self.assertNotIn('super-private', string)
        self.assertIn('PostgreSQL', string)


if __name__ == '__main__':
    unittest.main()
