"""v7.1.38: real ORM ownership, atomic removal, and notification regressions."""
import importlib
import pkgutil
import unittest
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.models import __path__ as model_paths
for item in pkgutil.iter_modules(model_paths):
    importlib.import_module('app.models.' + item.name)
from app.react_app.inbox import PruvsInboxRead
from app.models.user import User
from app.models.case import Case
from app.models.receipt_item import ReceiptItem
from app.models.document import Document
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.push_notification import PushEvent
from app.react_app import inbox
from app.react_app.security_rules import require_bill_access
from app.react_app.participant_removal import remove_participant
from app.react_app.bill_service import (
    get_split_bill_session_summary, get_joined_participants_count,
    join_split_bill_session_as_user, join_split_bill_session,
)


class RemoveParticipantTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.db.add_all([
            User(id=101, phone_number='+4010101', username='billowner', username_key='billowner', status='active', name='Owner'),
            User(id=202, phone_number='+4020202', username='participantb', username_key='participantb', status='active', name='Participant B', preferred_language='ro'),
            User(id=303, phone_number='+4030303', username='participantc', username_key='participantc', status='active', name='Participant C'),
            Case(id=1, user_id=101, status='processed', module='receipt'),
            SplitBillSession(id=10, case_id=1, owner_user_id=101, token='test-removal-token', status='open', expected_participants_count=3, expires_at=datetime.utcnow()+timedelta(days=2)),
            SplitBillParticipant(id=11, session_id=10, user_id=101, role='owner', status='joined', display_name='Owner', participant_token='owner-11'),
            SplitBillParticipant(id=22, session_id=10, user_id=202, role='participant', status='joined', display_name='Participant B', participant_token='b-22'),
            SplitBillParticipant(id=33, session_id=10, user_id=303, role='participant', status='joined', display_name='Participant C', participant_token='c-33'),
            Document(id=90, case_id=1, path='example.jpg', stored_filename='example.jpg'),
            ReceiptItem(id=100, case_id=1, document_id=90, name='Pizza', quantity=2, unit_price=12, total_price=24),
            SplitBillItemAssignment(id=1, session_id=10, participant_id=22, receipt_item_id=100, quantity=1, amount=12),
            SplitBillItemAssignment(id=2, session_id=10, participant_id=33, receipt_item_id=100, quantity=1, amount=12),
            PushEvent(id='existing-b', user_id=202, kind='reminder', title='Private restaurant', body='Sensitive 12 RON',
                      url='/bill/test-removal-token', status='pending', expires_at=datetime.utcnow()+timedelta(days=1)),
        ])
        self.db.commit()
        self.session = self.db.get(SplitBillSession, 10)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def remove(self, by=101, participant=22):
        return remove_participant(self.db, self.session, by, participant)

    def assert_rejected(self, expected, *, by=101, participant=22):
        with self.assertRaises(HTTPException) as raised:
            self.remove(by, participant)
        self.assertEqual(raised.exception.status_code, expected)
        self.assertEqual(self.db.get(SplitBillParticipant,22).status,'joined')
        self.assertEqual(self.db.query(SplitBillItemAssignment).count(),2)

    def test_owner_removes_unpaid_participant_and_releases_only_own_items(self):
        self.assertEqual(self.remove(),22)
        self.assertEqual(self.db.get(SplitBillParticipant,22).status,'removed')
        self.assertEqual(self.db.query(SplitBillItemAssignment).count(),1)
        self.assertEqual(self.db.query(SplitBillItemAssignment).first().participant_id,33)
        self.assertEqual(get_joined_participants_count(self.db,self.session),2)
        summary=get_split_bill_session_summary(self.db,self.session,ensure_translations=False)
        self.assertEqual(len(summary['participants']),2)
        self.assertEqual(summary['remaining_total'],12)
        self.assertEqual(summary['items'][0]['remaining_quantity'],1)
        self.assertFalse(summary['can_close'])

    def test_nonowner_cannot_remove_someone(self):
        self.assert_rejected(403,by=303)

    def test_owner_cannot_be_removed(self):
        with self.assertRaises(HTTPException) as raised: self.remove(participant=11)
        self.assertEqual(raised.exception.status_code,403)
        self.assertEqual(self.db.get(SplitBillParticipant,11).status,'joined')

    def test_other_session_and_nonexistent_ids_are_inaccessible(self):
        for pid in (999,0):
            with self.assertRaises(HTTPException) as raised: self.remove(participant=pid)
            self.assertIn(raised.exception.status_code,(400,404))
        self.assertEqual(self.db.query(SplitBillItemAssignment).count(),2)

    def test_boolean_ids_are_rejected(self):
        with self.assertRaises(HTTPException) as raised: self.remove(participant=True)
        self.assertEqual(raised.exception.status_code,400)

    def test_settled_bill_refuses_removal(self):
        self.session.status='settled';self.db.commit()
        self.assert_rejected(409)

    def test_reported_or_initiated_payment_refuses_removal(self):
        for payment in ('paid','received','initiated'):
            member=self.db.get(SplitBillParticipant,22)
            member.payment_status=payment
            self.db.commit()
            self.assert_rejected(409)

    def test_paid_at_refuses_removal_even_if_status_incorrect(self):
        member=self.db.get(SplitBillParticipant,22)
        member.paid_at=datetime.utcnow();self.db.commit()
        self.assert_rejected(409)

    def test_removed_membership_cannot_use_api_or_join_again(self):
        self.remove()
        with self.assertRaises(HTTPException) as raised: require_bill_access(self.db,self.session.token,202)
        self.assertEqual(raised.exception.status_code,404)
        with self.assertRaises(HTTPException) as raised: join_split_bill_session_as_user(self.db,self.session,self.db.get(User,202))
        self.assertEqual(raised.exception.status_code,403)
        with self.assertRaises(ValueError): join_split_bill_session(self.db,self.session,phone_number='+4020202')
        self.assertEqual(self.db.get(SplitBillParticipant,22).status,'removed')

    def test_removed_member_cannot_be_selected_for_removal_again(self):
        self.remove()
        with self.assertRaises(HTTPException) as raised:self.remove()
        self.assertEqual(raised.exception.status_code,404)
        self.assertEqual(self.db.query(PushEvent).filter_by(user_id=202,kind='participant_removed').count(),1)

    def test_other_joined_member_keeps_access_and_allocation(self):
        self.remove()
        self.assertEqual(require_bill_access(self.db,self.session.token,303)[1].id,33)
        summary=get_split_bill_session_summary(self.db,self.session,ensure_translations=False)
        self.assertEqual(summary['participants'][-1]['participant_id'],33)
        self.assertEqual(summary['items'][0]['assignments'][0]['participant_id'],33)

    def test_private_generic_notification_and_redacted_prior_inbox(self):
        self.remove()
        event=self.db.query(PushEvent).filter_by(kind='participant_removed',user_id=202).one()
        self.assertEqual(event.url,'/history')
        self.assertNotIn(self.session.token,event.title+event.body+event.url)
        self.assertNotIn('Pizza',event.title+event.body)
        result=inbox.messages(unread=False,offset=0,identity=(self.db.get(User,202),None),db=self.db)
        self.assertEqual(result['total'],2)
        self.assertTrue(any(x['kind']=='participant_removed' and not x['can_open'] for x in result['rows']))
        self.assertNotIn('Private restaurant',str(result))
        self.assertNotIn('Sensitive 12 RON',str(result))
        self.assertNotIn(self.session.token,str(result))

    def test_undelivered_prior_push_is_neutralized(self):
        self.remove()
        event=self.db.get(PushEvent,'existing-b')
        self.assertEqual(event.status,'in_app_only')
        self.assertEqual(event.url,'/history')
        self.assertNotIn('Sensitive',event.body)

    def test_no_notification_is_created_for_anonymous_guest(self):
        # guest is joined but not linked to any account
        guest=SplitBillParticipant(id=44,session_id=10,user_id=None,role='participant',status='joined',display_name='Guest',participant_token='guest-44')
        self.db.add(guest);self.db.commit()
        self.assertEqual(self.remove(participant=44),44)
        self.assertEqual(self.db.query(PushEvent).filter_by(kind='participant_removed').count(),0)

    def test_notification_is_english_for_english_account(self):
        self.remove(participant=33)
        event=self.db.query(PushEvent).filter_by(kind='participant_removed',user_id=303).one()
        self.assertEqual(event.title,'Shared bill access removed')

    def test_fixed_tip_recomputes_after_remove(self):
        self.session.tip_mode='fixed';self.session.tip_value=9;self.db.commit()
        before=get_split_bill_session_summary(self.db,self.session,ensure_translations=False)
        self.assertEqual(len(before['participants']),3)
        self.remove()
        after=get_split_bill_session_summary(self.db,self.session,ensure_translations=False)
        self.assertEqual(len(after['participants']),2)
        self.assertAlmostEqual(after['tip_total'],9)
        self.assertEqual(after['remaining_total'],12)

    def test_backend_route_checks_real_identity(self):
        # Direct route invocation; middleware CSRF is covered by existing auth tests.
        from app.react_app.api import remove_bill_participant
        with self.assertRaises(HTTPException) as raised:
            remove_bill_participant(self.session.token,22,identity=(self.db.get(User,303),None),db=self.db)
        self.assertEqual(raised.exception.status_code,403)
        result=remove_bill_participant(self.session.token,22,identity=(self.db.get(User,101),None),db=self.db)
        self.assertEqual(result['joined_participants_count'],2)

    def test_frontend_confirmation_and_routing_exist(self):
        from pathlib import Path
        frontend=Path(__file__).resolve().parents[1]/'frontend/src'
        bill=(frontend/'Bill.jsx').read_text()
        dialog=(frontend/'professional/RemoveParticipantDialog.jsx').read_text()
        self.assertIn("'/participants/' + removeTarget.participant_id",bill)
        self.assertIn("'DELETE'",bill)
        self.assertIn('role="dialog"',dialog)
        self.assertIn('aria-modal="true"',dialog)
        self.assertIn('onConfirm',dialog)

    def test_queued_event_is_blocked_by_provider_worker_after_revocation(self):
        from app.react_app.push_worker import deliver
        member = self.db.get(SplitBillParticipant,22)
        member.status='removed'
        old=self.db.get(PushEvent,'existing-b')
        old.status='processing'
        self.db.commit()
        deliver(self.db,old)
        self.assertEqual(old.status,'in_app_only')
        self.assertEqual(old.url,'/history')
        self.assertNotIn('Sensitive 12 RON',old.body)

    def test_revoked_member_cannot_use_invitation_preview(self):
        from app.react_app.api import invitation
        self.remove()
        with self.assertRaises(HTTPException) as raised:
            invitation(self.session.token,identity=(self.db.get(User,202),None),db=self.db)
        self.assertEqual(raised.exception.status_code,404)

if __name__=='__main__':unittest.main()
