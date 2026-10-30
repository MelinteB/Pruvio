"""v7.1.38: no provider network calls, data retained on SQL failure, bounded reads."""
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

from fastapi import HTTPException
import importlib
import pkgutil
from app.models import __path__ as model_paths
for entry in pkgutil.iter_modules(model_paths):
    importlib.import_module('app.models.' + entry.name)
from app.services import receipt_storage as storage
from app.services import document_service as documents


ENV = {'PRUVS_S3_ENDPOINT': 'https://objects.example.invalid',
       'PRUVS_S3_BUCKET': 'private-receipts',
       'PRUVS_S3_ACCESS_KEY_ID': 'test-id',
       'PRUVS_S3_SECRET_ACCESS_KEY': 'test-secret'}


class DummyDb:
    def __init__(self, fail=False):
        self.fail = fail
        self.commits = 0
        self.rollbacks = 0
    def add(self, obj):pass
    def commit(self):
        self.commits += 1
        if self.fail: raise RuntimeError('SQL unavailable')
    def rollback(self): self.rollbacks += 1


class ReceiptStorageTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.doc = SimpleNamespace(path='s3://private-receipts/users/8/receipts/42/file.jpg',
                                   stored_filename='file.jpg', mime_type='image/jpeg')
        self.case = SimpleNamespace(id=42)

    def test_ready_rejects_insecure_and_bad_endpoints_before_quota_use(self):
        self.assertTrue(storage.ready())
        for endpoint in ('http://objects.example.invalid', 'https://',
                         'https://user:pass@objects.example.invalid'):
            with self.subTest(endpoint=endpoint), patch.dict(os.environ, {'PRUVS_S3_ENDPOINT': endpoint}):
                self.assertFalse(storage.ready())

    def test_upload_refuses_unsafe_filenames_without_network_calls(self):
        with patch.object(storage, '_client') as provider:
            for filename in ('../x.jpg', 'folder/x.jpg', '..', 'bad\\name.pdf', '', 'bad\nname.pdf'):
                self.doc.stored_filename = filename
                with self.subTest(filename=filename), self.assertRaises(HTTPException) as error:
                    storage.store_paid(self.doc, self.case, 8, b'photo')
                self.assertEqual(error.exception.status_code, 409)
            provider.assert_not_called()

    def test_cloud_reads_reject_other_account_or_changed_bucket(self):
        with patch.object(storage, '_client') as provider:
            for user_id in (7, 999):
                with self.assertRaises(HTTPException) as error:
                    storage.read_paid(self.doc, user_id=user_id, case_id=42)
                self.assertEqual(error.exception.status_code, 409)
            provider.assert_not_called()

    def test_cloud_reads_are_bounded_even_without_content_length(self):
        class FakeBody:
            def __init__(self): self.limits=[];self.closed=False
            def read(self, count=-1):self.limits.append(count);return b'Z'*(storage.MAX_ORIGINAL_BYTES+1)
            def close(self):self.closed=True
        body=FakeBody();provider=Mock();provider.get_object.return_value={'Body':body}
        with patch.object(storage,'_client',return_value=provider):
            with self.assertRaises(HTTPException) as error:
                storage.read_paid(self.doc,user_id=8,case_id=42)
        self.assertEqual(error.exception.status_code,413)
        self.assertEqual(body.limits,[storage.MAX_ORIGINAL_BYTES+1])
        self.assertTrue(body.closed)

    def test_cloud_content_length_rejected_without_reading(self):
        body=Mock();provider=Mock()
        provider.get_object.return_value={'Body':body,'ContentLength':storage.MAX_ORIGINAL_BYTES+10}
        with patch.object(storage,'_client',return_value=provider):
            with self.assertRaises(HTTPException) as error:
                storage.read_paid(self.doc,user_id=8,case_id=42)
        self.assertEqual(error.exception.status_code,413)
        body.read.assert_not_called();body.close.assert_called_once()

    def test_valid_cloud_read_returns_exact_bytes(self):
        body=io.BytesIO(b'test image');provider=Mock()
        provider.get_object.return_value={'Body':body,'ContentLength':10}
        with patch.object(storage,'_client',return_value=provider):
            result=storage.read_paid(self.doc,user_id=8,case_id=42)
        self.assertEqual(result,b'test image')
        self.assertTrue(body.closed)

    def test_cloud_write_sql_failure_compensates_object_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as temp:
            original=Path(temp)/'receipt.jpg';original.write_bytes(b'image')
            doc=SimpleNamespace(path=str(original),stored_filename='file.jpg',mime_type='image/jpeg')
            with patch.object(storage,'store_paid',return_value='s3://private-receipts/users/8/receipts/42/file.jpg'), \
                 patch.object(storage,'delete_paid') as erase:
                db=DummyDb(fail=True)
                with self.assertRaisesRegex(RuntimeError,'SQL unavailable'):
                    storage.finalize_original(db,self.case,doc,8,'plus')
            self.assertEqual(doc.path,str(original));self.assertTrue(original.exists())
            self.assertEqual(db.rollbacks,1);erase.assert_called_once()

    def test_cloud_cleanup_failure_reported_not_swallowed(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'receipt.jpg';path.write_bytes(b'data')
            doc=SimpleNamespace(path=str(path),stored_filename='file.jpg',mime_type='image/jpeg')
            with patch.object(storage,'store_paid',return_value='s3://private-receipts/users/8/receipts/42/file.jpg'), \
                 patch.object(storage,'delete_paid',side_effect=RuntimeError('provider unavailable')):
                with self.assertRaises(HTTPException) as error:
                    storage.finalize_original(DummyDb(fail=True),self.case,doc,8,'plus')
            self.assertEqual(error.exception.status_code,503)
            self.assertTrue(path.exists())

    def test_cloud_success_commits_then_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'photo.jpg';p.write_bytes(b'photo')
            doc=SimpleNamespace(path=str(p),stored_filename='file.jpg',mime_type='image/jpeg')
            db=DummyDb()
            with patch.object(storage,'store_paid',return_value='s3://private-receipts/users/8/receipts/42/file.jpg'), \
                 patch.object(storage,'_cleanup_after_commit') as cleanup:
                result=storage.finalize_original(db,self.case,doc,8,'plus')
            self.assertEqual(result,'cloud');self.assertEqual(db.commits,1)
            self.assertEqual(doc.path,'s3://private-receipts/users/8/receipts/42/file.jpg')
            cleanup.assert_called_once_with(p)

    def test_atomic_original_write_cleans_failed_write(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'abc.jpg'
            documents._atomic_write_original(target,b'content')
            self.assertEqual(target.read_bytes(),b'content')
            self.assertEqual([p for p in Path(temp).iterdir() if p.name.startswith('.pruvs-upload-')],[])

    def test_document_db_failure_removes_orphan_file(self):
        from app.models.case import Case
        with tempfile.TemporaryDirectory() as temp:
            case=SimpleNamespace(id=7)
            db=DummyDb(fail=True)
            with patch.object(documents,'upload_root',return_value=Path(temp)):
                with self.assertRaisesRegex(RuntimeError,'SQL unavailable'):
                    documents.save_document_bytes(db,case,b'not-a-real-jpeg','scan.jpg','image/jpeg','receipt')
                self.assertEqual(list((Path(temp)/'case_7').iterdir()),[])
            self.assertEqual(db.rollbacks,1)


class BackupReadinessTests(unittest.TestCase):
    def test_backup_magic_and_sha_only(self):
        from scripts.recovery_readiness import inspect_backup
        with tempfile.TemporaryDirectory() as temp:
            backup=Path(temp)/'safe.dump';backup.write_bytes(b'PGDMP'+b'12345')
            checksum=hashlib.sha256(backup.read_bytes()).hexdigest()
            status=inspect_backup(backup,checksum)
            self.assertTrue(status['sha256_verified'])
            self.assertFalse(status['isolated_restore_verified'])
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                inspect_backup(backup,'0'*64)
            backup.write_bytes(b'garbage')
            with self.assertRaisesRegex(ValueError,'custom-format'):
                inspect_backup(backup,hashlib.sha256(backup.read_bytes()).hexdigest())

    def test_toc_listing_is_read_only(self):
        from scripts.recovery_readiness import inspect_backup
        with tempfile.TemporaryDirectory() as temp:
            backup=Path(temp)/'dump';backup.write_bytes(b'PGDMPok')
            sha=hashlib.sha256(backup.read_bytes()).hexdigest()
            with patch('scripts.recovery_readiness.shutil.which',return_value='/usr/bin/pg_restore'), \
                 patch('scripts.recovery_readiness.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'TOC item',stderr=b'')) as run:
                status=inspect_backup(backup,sha,check_toc=True)
            self.assertTrue(status['toc_verified'])
            cmd=run.call_args.args[0]
            self.assertEqual(cmd[1],'--list')
            self.assertNotIn('--dbname',cmd)
            self.assertFalse(status['isolated_restore_verified'])

if __name__=='__main__':unittest.main()

class CreditReservationRecoveryTests(unittest.TestCase):
    """Exercise existing v7.1.35 quota logic, not a new billing mechanism."""
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.database import Base
        self.database_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.database_dir.cleanup)
        self.engine = create_engine('sqlite:///' + str(Path(self.database_dir.name)/'quota-test.db'))
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.session_factory()
        self.addCleanup(self.db.close)
        from app.react_app import usage
        self.usage = usage
        self.patcher = patch.object(usage, 'SessionLocal', self.session_factory)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_failed_ocr_refunds_credits_exactly_once(self):
        from app.models.pruvs_commerce import CreditEntry
        from app.models.pruvs_usage import PruvsMeteredUse
        self.db.add(CreditEntry(user_id=9,delta=8,reference='seed',reason='seed'))
        self.db.commit()
        with patch.object(self.usage, 'credit_costs', return_value={'ocr':2,'expense_report':5}):
            token = self.usage.reserve(9,'ocr',{'free': {'ocr_allowance':0}},'free',use_credits=True)
        self.assertEqual(self.usage.credit_balance(self.db,9),6)
        self.usage.finish(token,False)
        self.usage.finish(token,False)
        self.db.expire_all()
        self.assertEqual(self.usage.credit_balance(self.db,9),8)
        self.assertEqual(self.db.query(CreditEntry).filter_by(reference='usage-refund:'+token).count(),1)
        self.assertEqual(self.db.query(PruvsMeteredUse).filter_by(token=token).one().state,'cancelled')

    def test_successful_ocr_charges_only_once(self):
        from app.models.pruvs_commerce import CreditEntry
        self.db.add(CreditEntry(user_id=9,delta=8,reference='seed',reason='seed'))
        self.db.commit()
        with patch.object(self.usage, 'credit_costs', return_value={'ocr':2,'expense_report':5}):
            token = self.usage.reserve(9,'ocr',{'free': {'ocr_allowance':0}},'free',use_credits=True)
        self.usage.finish(token,True)
        self.usage.finish(token,True)
        self.usage.finish(token,False)
        self.db.expire_all()
        self.assertEqual(self.usage.credit_balance(self.db,9),6)
        self.assertEqual(self.db.query(CreditEntry).filter_by(reference='usage-charge:'+token).count(),1)
        self.assertEqual(self.db.query(CreditEntry).filter_by(reference='usage-refund:'+token).count(),0)

    def test_denied_reservation_does_not_charge(self):
        from app.models.pruvs_commerce import CreditEntry
        from app.models.pruvs_usage import PruvsMeteredUse
        with patch.object(self.usage, 'credit_costs', return_value={'ocr':2,'expense_report':5}):
            with self.assertRaises(HTTPException) as error:
                self.usage.reserve(9,'ocr',{'free': {'ocr_allowance':0}},'free',use_credits=False)
        self.assertEqual(error.exception.status_code,402)
        self.assertEqual(self.db.query(CreditEntry).count(),0)
        self.assertEqual(self.db.query(PruvsMeteredUse).count(),0)
