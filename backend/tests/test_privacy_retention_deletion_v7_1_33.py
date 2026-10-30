"""v7.1.33 account deletion: two-user SQLite, storage, and billing safeguards."""
import importlib
import os
import pkgutil
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.models import __path__ as model_paths
for entry in pkgutil.iter_modules(model_paths):
    importlib.import_module('app.models.' + entry.name)
from app.react_app.inbox import PruvsInboxRead  # Register startup model before create_all
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.receipt_fingerprint import ReceiptFingerprint
from app.models.receipt_identity import ReceiptIdentity
from app.models.payment_profile import PaymentProfile
from app.models.pruvs_commerce import CreditEntry, Referral, RewardVoucher
from app.models.pruvs_billing import PruvsStripeAccount, PruvsInvoiceEmail
from app.models.pruvs_usage import PruvsMeteredUse
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.push_notification import PushEvent, PushDevice
from app.services.account_service import delete_user_completely
from app.services.account_deletion import inspect_account, deletion_plan


class PrivacyAccountDeletionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.db.add_all([
            User(id=101, phone_number='+4001001', username='owner', username_key='owner',
                 status='active', is_email_verified=True, email='owner@local.test'),
            User(id=202, phone_number='+4002002', username='guest', username_key='guest',
                 status='active', is_email_verified=True, email='guest@local.test'),
            Case(id=1001, user_id=101, module='receipt', status='processed'),
            Case(id=2002, user_id=202, module='receipt', status='processed'),
            Document(id=1, case_id=1001, path='s3://receipt-bucket/users/101/receipts/1001/a.jpg', stored_filename='a.jpg'),
            Document(id=2, case_id=2002, path='s3://receipt-bucket/users/202/receipts/2002/b.jpg', stored_filename='b.jpg'),
            ReceiptItem(id=11, case_id=1001, document_id=1, name='Pasta', total_price=20),
            ReceiptItem(id=22, case_id=2002, document_id=2, name='Secret dish', total_price=40),
            ReceiptFingerprint(user_id=101, case_id=1001, sha256='a'*64),
            ReceiptIdentity(user_id=101, case_id=1001, identity_hash='b'*64),
            CreditEntry(user_id=101, delta=3, reason='test', reference='test-101'),
            CreditEntry(user_id=202, delta=7, reason='test', reference='test-202'),
            PruvsMeteredUse(user_id=101, resource='ocr', month='2026-10',
                            token='token-101', state='completed', paid_with='allowance'),
            PaymentProfile(user_id=101, label='My bank', recipient_name='Me', iban='RO012345678901234567'),
            SplitBillSession(id=10, case_id=2002, owner_user_id=202,
                             token='secret-split', status='settled'),
            SplitBillParticipant(id=60, session_id=10, user_id=101, status='joined', role='participant',
                                 participant_token='t-101', display_name='Owner'),
            SplitBillParticipant(id=61, session_id=10, user_id=202, status='joined', role='owner',
                                 participant_token='t-202', display_name='Guest'),
            PushEvent(id='event101', user_id=101, kind='bill', title='Sample', body='Secret', url='/bill/demo',
                      status='pending', expires_at=__import__('datetime').datetime(2026, 11, 1)),
        ])
        self.db.commit()
        self.env=patch.dict(os.environ, {'PRUVS_S3_BUCKET':'receipt-bucket'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.close()
        self.engine.dispose()

    def test_preview_counts_only_user_owned_records(self):
        me=inspect_account(self.db, self.db.get(User, 101))
        self.assertTrue(me['can_delete'])
        self.assertEqual(me['receipts'],1)
        self.assertEqual(me['receipt_documents'],1)
        self.assertEqual(me['cloud_receipts'],1)
        self.assertEqual(me['joined_splits'],1)
        self.assertNotIn('Secret dish',str(me))
        self.assertNotIn('secret-split',str(me))
        self.assertNotIn('guest@local.test',str(me))

    def test_deletion_erases_owned_cloud_and_dependent_rows_but_not_another_user(self):
        deleted=[]
        with patch('app.services.receipt_storage.delete_paid', side_effect=lambda doc: deleted.append(doc.path)):
            delete_user_completely(self.db,self.db.get(User,101))
        self.assertEqual(deleted,['s3://receipt-bucket/users/101/receipts/1001/a.jpg'])
        self.assertIsNone(self.db.get(User,101))
        self.assertIsNotNone(self.db.get(User,202))
        self.assertIsNone(self.db.get(Case,1001))
        self.assertIsNotNone(self.db.get(Case,2002))
        self.assertEqual(self.db.query(ReceiptFingerprint).count(),0)
        self.assertEqual(self.db.query(ReceiptIdentity).count(),0)
        self.assertEqual(self.db.query(PaymentProfile).count(),0)
        self.assertEqual(self.db.query(PruvsMeteredUse).count(),0)
        self.assertEqual(self.db.query(PushEvent).filter_by(user_id=101).count(),0)
        self.assertEqual(self.db.query(CreditEntry).filter_by(user_id=101).count(),0)
        self.assertEqual(self.db.query(CreditEntry).filter_by(user_id=202).count(),1)
        self.assertEqual(self.db.query(SplitBillParticipant).filter_by(user_id=202).count(),1)
        self.assertEqual(self.db.query(SplitBillParticipant).filter_by(user_id=101).count(),0)

    def test_storage_provider_failure_does_not_delete_database_rows(self):
        with patch('app.services.receipt_storage.delete_paid', side_effect=RuntimeError('private provider detail')):
            with self.assertRaises(HTTPException) as exc:
                delete_user_completely(self.db,self.db.get(User,101))
        self.assertEqual(exc.exception.status_code,503)
        self.assertNotIn('private provider detail',exc.exception.detail)
        self.assertIsNotNone(self.db.get(User,101))
        self.assertIsNotNone(self.db.get(Document,1))

    def test_modified_cloud_path_is_rejected_before_external_call(self):
        doc=self.db.get(Document,1)
        doc.path='s3://receipt-bucket/users/202/receipts/2002/b.jpg'
        self.db.commit()
        with patch('app.services.receipt_storage.delete_paid') as remove:
            with self.assertRaises(HTTPException) as exc:
                delete_user_completely(self.db,self.db.get(User,101))
            remove.assert_not_called()
        self.assertEqual(exc.exception.status_code,409)
        self.assertIsNotNone(self.db.get(User,101))

    def test_cloud_bucket_mismatch_is_rejected(self):
        self.db.get(Document,1).path='s3://wrong-bucket/users/101/receipts/1001/a.jpg'
        self.db.commit()
        with self.assertRaises(HTTPException) as exc:
            deletion_plan(self.db,self.db.get(User,101))
        self.assertEqual(exc.exception.status_code,409)

    def test_billing_customer_blocks_deletion_before_storage(self):
        self.db.add(PruvsStripeAccount(user_id=101,customer_id='cus_test',status='active'))
        self.db.commit()
        self.assertTrue(inspect_account(self.db,self.db.get(User,101))['billing_review_required'])
        with patch('app.services.receipt_storage.delete_paid') as remove:
            with self.assertRaises(HTTPException) as exc:
                delete_user_completely(self.db,self.db.get(User,101))
            remove.assert_not_called()
        self.assertEqual(exc.exception.status_code,409)
        self.assertIsNotNone(self.db.get(User,101))

    def test_invoice_records_block_deletion(self):
        self.db.add(PruvsInvoiceEmail(invoice_id='inv_test',user_id=101,email='owner@local.test'))
        self.db.commit()
        preview=inspect_account(self.db,self.db.get(User,101))
        self.assertFalse(preview['can_delete'])
        self.assertEqual(preview['blockers'][0][:15],'Billing records')

    def test_owned_split_removes_only_affected_membership_and_history(self):
        from app.models.history_visibility import HistoryVisibility
        # This user's owned case has a shared bill, while the other account
        # also owns an unrelated bill. Deleting one account must not delete the other.
        self.db.add_all([
            SplitBillSession(id=30, case_id=1001, owner_user_id=101,
                             token='owned-bill', status='settled'),
            SplitBillParticipant(id=70, session_id=30, user_id=202, status='joined',
                                 role='participant', participant_token='guest-owned', display_name='Guest'),
            HistoryVisibility(user_id=202, kind='bill', source_id=30, state='archived'),
            HistoryVisibility(user_id=202, kind='bill', source_id=10, state='archived'),
        ])
        self.db.commit()
        with patch('app.services.receipt_storage.delete_paid'):
            delete_user_completely(self.db,self.db.get(User,101))
        self.assertIsNone(self.db.get(SplitBillSession,30))
        self.assertIsNotNone(self.db.get(SplitBillSession,10))
        self.assertEqual(self.db.query(HistoryVisibility).filter_by(user_id=202,kind='bill',source_id=30).count(),0)
        self.assertEqual(self.db.query(HistoryVisibility).filter_by(user_id=202,kind='bill',source_id=10).count(),1)

    def test_explicit_receipt_delete_denies_wrong_cloud_key(self):
        from app.services.receipt_cleanup import delete_case
        self.db.get(Document,1).path='s3://receipt-bucket/users/202/receipts/2002/b.jpg'
        self.db.commit()
        with patch('app.services.receipt_storage.delete_paid') as remove:
            with self.assertRaises(HTTPException) as exc:
                delete_case(self.db,1001,strict=False)
            remove.assert_not_called()
        self.assertEqual(exc.exception.status_code,409)
        self.assertIsNotNone(self.db.get(Case,1001))

    def test_preview_flags_unsafe_storage(self):
        self.db.get(Document,1).path='s3://receipt-bucket/users/202/receipts/2002/b.jpg'
        self.db.commit()
        preview=inspect_account(self.db,self.db.get(User,101))
        self.assertFalse(preview['can_delete'])
        self.assertTrue(preview['blockers'])

    def test_release_gate_scopes_retention_example_without_opening_config(self):
        from pathlib import Path
        from scripts.launch_control import releases_to_stage, GateError
        import tempfile, json, hashlib
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as work:
            project=Path(work)
            artifact=project/'backend/config/retention-policy.example.json'
            artifact.parent.mkdir(parents=True)
            artifact.write_text('demo', encoding='utf8')
            update=project/'updates/pruvs_v7_1_33_test'
            update.mkdir(parents=True)
            good={'config/retention-policy.example.json':{'text':True,
                  'updated_sha256': hashlib.sha256(b'demo').hexdigest()}}
            (update/'manifest.json').write_text(json.dumps({'files':good}),encoding='utf8')
            paths,_=releases_to_stage(project,'7.1.33','7.1.33')
            self.assertIn('backend/config/retention-policy.example.json',paths)
            secret=project/'backend/config/production.env'
            secret.write_text('secret',encoding='utf8')
            (update/'manifest.json').write_text(json.dumps({'files':{
                'config/production.env':{'text':True,'updated_sha256':hashlib.sha256(b'secret').hexdigest()}}}),encoding='utf8')
            with self.assertRaisesRegex(GateError,'Unsafe release path'):
                releases_to_stage(project,'7.1.33','7.1.33')

    def test_launch_control_uses_windows_npm_cmd_and_current_python(self):
        import sys
        from scripts.launch_control import resolved_command
        self.assertEqual(resolved_command(['npm', 'test'], windows=True,
            which=lambda x: 'C:/Node/npm.cmd' if x == 'npm.cmd' else None),
            ['C:/Node/npm.cmd', 'test'])
        self.assertEqual(resolved_command(['python','-V'], windows=True)[0], sys.executable)
        self.assertEqual(resolved_command(['npm','run','build'], windows=False), ['npm','run','build'])

    def test_retention_policy_review_is_read_only_and_unapproved(self):
        from pathlib import Path
        from scripts.retention_review import review, CATEGORIES
        root=Path(__file__).resolve().parents[1]
        config=root/'config/retention-policy.example.json'
        original=config.read_bytes()
        result=review(config)
        self.assertEqual(result['status'], 'manual_review_required')
        self.assertEqual(result['categories_expected'],len(CATEGORIES))
        self.assertEqual(len(result['categories_incomplete']),len(CATEGORIES))
        self.assertFalse(result['automatic_deletion_enabled'])
        self.assertEqual(original,config.read_bytes())

    def test_no_automatic_retention_job_and_current_legal_blocker_remains(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        script=(root/'scripts/privacy_readiness.py').read_text(encoding='utf8')
        legal=(root/'app/legal_content.py').read_text(encoding='utf8')
        self.assertIn('Retention jobs remain disabled',script)
        self.assertIn('This prototype does not yet define final retention periods',legal)
        api=(root/'app/react_app/api.py').read_text(encoding='utf8')
        self.assertIn("@router.get('/account/delete/preview')",api)
        self.assertIn('identity=Depends(current)',api)
        self.assertIn('deletion_plan(db,u)',api)
        self.assertIn('accounts.delete_user_completely(db,u)',api)
        frontend=(root/'frontend/src/Account.jsx').read_text(encoding='utf8')
        self.assertIn("request('/account/delete/preview')",frontend)
        self.assertIn('Preview account deletion',frontend)
        self.assertIn('Previzualizează ștergerea contului',(root/'frontend/src/i18n.js').read_text(encoding='utf8'))

if __name__=='__main__':unittest.main()
