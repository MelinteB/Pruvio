"""v7.1.26: real SQLite transaction, permission, event, and notification regressions."""
import importlib
import pkgutil
import unittest
# Optional SDK is not exercised by the payment tests in minimal/offline runners.
import openai
if not hasattr(openai, "OpenAI"):
    openai.OpenAI = object
from unittest.mock import patch
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.models import __path__ as model_paths
for module in pkgutil.iter_modules(model_paths):
    importlib.import_module('app.models.' + module.name)
from app.models.user import User
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.payment_confirmation_event import PaymentConfirmationEvent
from app.models.push_notification import PushEvent
# In isolated runners without Azure OCR SDK, avoid importing receipt OCR code in
# an event-notification test. This fake module lives only in this test process.
import sys
import types
import importlib.util
if importlib.util.find_spec('azure') is None:
    receipt_labels = types.ModuleType('app.react_app.receipt_labels')
    receipt_labels.receipt_label = lambda db, case_id: 'Test Cafe'
    sys.modules['app.react_app.receipt_labels'] = receipt_labels
from app.react_app import events
from app.react_app import payment_confirmation as payment
from app.react_app import bill_service as bills


class PaymentConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.db.add_all([
            User(id=81, phone_number='+40000000081', username='owner', username_key='owner', name='Owner', status='active'),
            User(id=82, phone_number='+40000000082', username='guest', username_key='guest', name='Guest', status='active'),
            User(id=83, phone_number='+40000000083', username='stranger', username_key='stranger', name='Stranger', status='active'),
            SplitBillSession(id=501, case_id=777, owner_user_id=81, token='test_501', status='settled', currency='RON', expected_participants_count=2),
            SplitBillSession(id=502, case_id=778, owner_user_id=83, token='test_502', status='settled', currency='RON', expected_participants_count=1),
            SplitBillParticipant(id=601, session_id=501, user_id=81, display_name='Owner', participant_token='pt_owner', role='owner', status='joined'),
            SplitBillParticipant(id=602, session_id=501, user_id=82, display_name='Guest', participant_token='pt_guest', role='participant', status='joined'),
            SplitBillParticipant(id=603, session_id=502, user_id=83, display_name='Stranger', participant_token='pt_stranger', role='owner', status='joined'),
        ])
        self.db.commit()
        self.s = self.db.get(SplitBillSession, 501)
        self.p = self.db.get(SplitBillParticipant, 602)
        self.snapshot = {'participants': [
            {'participant_id':601,'total':10}, {'participant_id':602,'total':125.50},
        ]}
        self.stub_a = patch.object(payment, 'get_split_bill_session_summary', return_value=self.snapshot)
        self.stub_b = patch.object(bills, 'get_split_bill_session_summary', return_value=self.snapshot)
        self.stub_c = patch('app.react_app.events.receipt_label', return_value='Test Cafe')
        self.stub_a.start(); self.stub_b.start(); self.stub_c.start()

    def tearDown(self):
        self.stub_a.stop();self.stub_b.stop();self.stub_c.stop()
        self.db.close();self.engine.dispose()

    def event_types(self):
        return [e.event_type for e in self.db.query(PaymentConfirmationEvent).order_by(PaymentConfirmationEvent.id).all()]

    def report(self, method='bank_transfer'):
        bills.record_participant_payment_status(self.db,self.s,self.p.id,method,True)
        self.db.refresh(self.p)

    def test_complete_lifecycle_and_exact_amount_audit(self):
        self.report()
        self.assertEqual(self.p.payment_status,'paid')
        self.assertEqual(self.event_types(),['reported'])
        self.assertEqual(str(self.db.query(PaymentConfirmationEvent).first().amount), '125.50')
        self.assertTrue(payment.acknowledge(self.db,self.s,self.p.id,81))
        self.db.refresh(self.p)
        self.assertEqual(self.p.payment_status,'received')
        self.assertEqual(self.p.confirmed_by_user_id,81)
        self.assertIsNotNone(self.p.received_at)
        self.assertEqual(self.event_types(), ['reported','received'])
        self.assertFalse(payment.acknowledge(self.db,self.s,self.p.id,81))
        self.assertEqual(self.event_types(), ['reported','received'])
        self.assertTrue(payment.acknowledge(self.db,self.s,self.p.id,81,reverse=True))
        self.assertEqual(self.p.payment_status,'paid')
        self.assertIsNone(self.p.received_at)
        self.assertFalse(payment.acknowledge(self.db,self.s,self.p.id,81,reverse=True))
        self.assertEqual(self.event_types(), ['reported','received','receipt_reversed'])
        self.assertTrue(payment.withdraw(self.db,self.s,self.p.id,82))
        self.assertEqual(self.p.payment_status,'unpaid')
        self.assertIsNone(self.p.paid_at)
        self.assertEqual(self.event_types(), ['reported','received','receipt_reversed','withdrawn'])
        self.assertFalse(payment.withdraw(self.db,self.s,self.p.id,82))

    def test_owner_requires_report_before_acknowledge(self):
        with self.assertRaisesRegex(ValueError,'report payment'):
            payment.acknowledge(self.db,self.s,self.p.id,81)
        self.assertEqual(self.event_types(), [])

    def test_nonowner_cannot_acknowledge_or_reverse(self):
        self.report()
        with self.assertRaises(PermissionError):
            payment.acknowledge(self.db,self.s,self.p.id,82)
        with self.assertRaises(PermissionError):
            payment.acknowledge(self.db,self.s,self.p.id,82,reverse=True)
        self.assertEqual(self.p.payment_status,'paid')

    def test_cross_session_participant_denied(self):
        self.report()
        with self.assertRaisesRegex(ValueError,'joined participant'):
            payment.acknowledge(self.db,self.s,603,81)
        self.assertEqual(self.event_types(),['reported'])

    def test_unsettled_actions_denied(self):
        self.s.status='open';self.db.commit()
        with self.assertRaisesRegex(ValueError,'Settle'):
            payment.acknowledge(self.db,self.s,self.p.id,81)
        with self.assertRaisesRegex(ValueError,'Settle'):
            payment.withdraw(self.db,self.s,self.p.id,82)

    def test_received_cannot_be_downgraded_or_withdrawn_by_participant(self):
        self.report()
        payment.acknowledge(self.db,self.s,self.p.id,81)
        with self.assertRaisesRegex(ValueError,'owner'):
            payment.withdraw(self.db,self.s,self.p.id,82)
        bills.record_participant_payment_status(self.db,self.s,self.p.id,'payment_link',False)
        bills.record_participant_payment_status(self.db,self.s,self.p.id,'bank_transfer',True)
        self.assertEqual(self.p.payment_status,'received')
        self.assertEqual(self.event_types(),['reported','received'])

    def test_cash_payment_report(self):
        self.report('cash')
        self.assertEqual(self.p.payment_method,'cash')
        self.assertEqual(self.event_types(),['reported'])

    def test_owner_cannot_report_payments_to_self(self):
        with self.assertRaisesRegex(ValueError,'participants'):
            bills.record_participant_payment_status(self.db,self.s,601,'cash',True)
        self.assertEqual(self.event_types(),[])

    def test_audit_history_scoped_to_bill_and_no_phone_data(self):
        self.report()
        rows=payment.history(self.db,self.s)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['actor_role'],'participant')
        self.assertEqual(rows[0]['amount'],'125.50')
        self.assertFalse(any('phone' in str(k) for k in rows[0]))
        self.assertEqual(payment.history(self.db,self.db.get(SplitBillSession,502)),[])

    def test_api_authorization_and_boolean_id_rejection(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parents[1]/'app/react_app/api.py').read_text()
        self.assertIn("owner=action not in ('payment', 'withdraw_payment')",source)
        self.assertIn("type(body.get('participant_id')) is not int",source)
        self.assertIn("s,_=member(db,token,identity[0].id)",source)
        self.assertIn("'/bills/{token}/payment-history'",source)

    def test_new_notifications_are_user_scoped(self):
        self.report()
        payment.acknowledge(self.db,self.s,self.p.id,81)
        recipients=[(e.user_id,e.kind) for e in self.db.query(PushEvent).all()]
        self.assertIn((81,'payment_marked'),recipients)
        self.assertIn((82,'payment_received'),recipients)
        self.assertNotIn(83,[uid for uid,_ in recipients])

    def test_report_retries_do_not_change_method_or_create_duplicate_events(self):
        self.report('bank_transfer')
        self.report('cash')
        self.assertEqual(self.p.payment_method, 'bank_transfer')
        self.assertEqual(self.event_types(), ['reported'])

    def test_receipt_confirmed_cannot_be_reset_by_reminder(self):
        self.report()
        payment.acknowledge(self.db, self.s, self.p.id, 81)
        with self.assertRaisesRegex(ValueError, 'Reverse the receipt'):
            bills.send_participant_reminder(self.db, self.s, 81, self.p.id, 'Please check')
        self.assertEqual(self.p.payment_status, 'received')
        self.assertEqual(self.event_types(), ['reported','received'])

    def test_reopen_resets_status_but_keeps_audit(self):
        self.report()
        payment.acknowledge(self.db, self.s, self.p.id, 81)
        with patch('app.react_app.events.enqueue_transition'):
            bills.reopen_split_bill_session(self.db,self.s,81)
        self.db.refresh(self.p)
        self.assertEqual(self.p.payment_status,'unpaid')
        self.assertIsNone(self.p.received_at)
        self.assertEqual(self.event_types(), ['reported','received','reopened_reset'])

    def test_reverse_and_withdraw_create_notifications_for_correct_accounts(self):
        self.report()
        payment.acknowledge(self.db,self.s,self.p.id,81)
        payment.acknowledge(self.db,self.s,self.p.id,81,reverse=True)
        payment.withdraw(self.db,self.s,self.p.id,82)
        kinds={(row.user_id,row.kind) for row in self.db.query(PushEvent).all()}
        self.assertIn((82,'payment_receipt_reversed'),kinds)
        self.assertIn((81,'payment_withdrawn'),kinds)

    def test_status_event_kinds_are_enabled_for_inbox_email(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        inbox=(root/'app/react_app/inbox.py').read_text()
        worker=(root/'app/react_app/push_worker.py').read_text()
        for kind in ('payment_received','payment_receipt_reversed','payment_withdrawn'):
            self.assertIn(kind, inbox)
            self.assertIn(kind, worker)

    def test_migration_is_additive_and_idempotent(self):
        import app.db.database as database
        eng=create_engine('sqlite:///:memory:')
        with eng.begin() as c:
            c.execute(text('CREATE TABLE split_bill_participants (id INTEGER PRIMARY KEY, paid_at TIMESTAMP NULL)'))
        with patch.object(database,'engine',eng):
            database.ensure_compatibility_schema()
            database.ensure_compatibility_schema()
        names={row['name'] for row in inspect(eng).get_columns('split_bill_participants')}
        self.assertIn('received_at',names)
        self.assertIn('confirmed_by_user_id',names)
        eng.dispose()


if __name__=='__main__': unittest.main()
