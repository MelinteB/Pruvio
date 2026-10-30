"""v7.1.34: cross-user resource isolation and constrained file-serving tests."""
import importlib
import importlib.util
import sys
import types
import pkgutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.models import __path__ as model_paths

for module in pkgutil.iter_modules(model_paths):
    importlib.import_module('app.models.' + module.name)

from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.push_notification import PushEvent
from app.react_app.inbox import PruvsInboxRead
from app.react_app import inbox, admin_api
from app.models.react_session import ReactSession
from app.react_app.auth import admin, current, digest
from app.react_app.security_rules import require_bill_access, invitation_is_current, joined_member
from app.services.document_service import resolve_document_path


class SecurityAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = Path(self.temp.name) / 'uploads'
        self.storage.mkdir()
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.now = datetime.utcnow()
        self.db.add_all([
            User(id=101, phone_number='+40000101', username='owner_a', username_key='owner_a',
                 name='Owner A', status='active', is_admin=False),
            User(id=202, phone_number='+40000202', username='member_b', username_key='member_b',
                 name='Member B', status='active', is_admin=False),
            User(id=303, phone_number='+40000303', username='stranger_c', username_key='stranger_c',
                 name='Stranger C', status='active', is_admin=False),
            User(id=404, phone_number='+40000404', username='admin_d', username_key='admin_d',
                 name='Admin D', status='active', is_admin=True),
            Case(id=111, user_id=101, module='receipt', status='processed'),
            Case(id=222, user_id=303, module='receipt', status='processed'),
            SplitBillSession(id=1001, case_id=111, owner_user_id=101, token='secret-bill-a',
                             status='settled', expires_at=self.now+timedelta(days=1)),
            SplitBillSession(id=2002, case_id=222, owner_user_id=303, token='secret-bill-c',
                             status='open', expires_at=self.now-timedelta(days=1)),
            SplitBillParticipant(id=11, session_id=1001, user_id=101, role='owner',
                                 status='joined', display_name='Owner A',participant_token='a'),
            SplitBillParticipant(id=22, session_id=1001, user_id=202, role='participant',
                                 status='joined',display_name='Member B',participant_token='b'),
            SplitBillParticipant(id=33, session_id=2002, user_id=303, role='owner',
                                 status='joined',display_name='Stranger C',participant_token='c'),
            PushEvent(id='evt_member', user_id=202, kind='payment_received',
                      title='Bank balance: sensitive', body='Private receipt amount 123.45 RON',
                      url='/bill/secret-bill-a', status='pending',
                      expires_at=self.now+timedelta(days=1)),
            PushEvent(id='evt_foreign', user_id=303, kind='payment_received',
                      title='Do not see', body='Other account secret',
                      url='/bill/secret-bill-c', status='pending',
                      expires_at=self.now+timedelta(days=1)),
        ])
        self.db.commit()
        self.storage_patch=patch('app.services.document_service.upload_root',return_value=self.storage)
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_owner_and_joined_member_can_read_their_bill(self):
        session, owner=require_bill_access(self.db,'secret-bill-a',101)
        self.assertEqual((session.id,owner.id),(1001,11))
        self.assertEqual(require_bill_access(self.db,'secret-bill-a',202)[1].id,22)

    def test_missing_and_foreign_bill_are_indistinguishable(self):
        for token in ('no-such-bill', 'secret-bill-a'):
            with self.assertRaises(HTTPException) as raised:
                require_bill_access(self.db,token,303)
            self.assertEqual(raised.exception.status_code,404)
            self.assertEqual(raised.exception.detail,'Bill not found.')

    def test_nonowner_cannot_perform_owner_action(self):
        with self.assertRaises(HTTPException) as raised:
            require_bill_access(self.db,'secret-bill-a',202,owner=True)
        self.assertEqual(raised.exception.status_code,403)
        self.assertEqual(require_bill_access(self.db,'secret-bill-a',101,owner=True)[0].id,1001)

    def test_removed_participant_has_no_bill_access(self):
        participant=self.db.get(SplitBillParticipant,22)
        participant.status='removed';self.db.commit()
        self.assertIsNone(joined_member(self.db,1001,202))
        with self.assertRaises(HTTPException) as raised:
            require_bill_access(self.db,'secret-bill-a',202)
        self.assertEqual(raised.exception.status_code,404)

    def test_removed_member_cannot_rejoin_with_old_invitation(self):
        from app.react_app.bill_service import join_split_bill_session_as_user
        session = self.db.get(SplitBillSession,1001)
        session.status = 'open'
        self.db.get(SplitBillParticipant,22).status='removed'
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            join_split_bill_session_as_user(self.db,session,self.db.get(User,202))
        self.assertEqual(raised.exception.status_code,403)
        self.assertEqual(self.db.get(SplitBillParticipant,22).status,'removed')

    def test_expired_invitation_cannot_grant_new_membership(self):
        self.assertFalse(invitation_is_current(self.db.get(SplitBillSession,2002)))
        self.assertTrue(invitation_is_current(self.db.get(SplitBillSession,1001)))
        self.assertFalse(invitation_is_current(self.db.get(SplitBillSession,1001),now=self.now+timedelta(days=2)))
        # Expiring the bearer invitation does not revoke an existing member's history.
        self.assertEqual(require_bill_access(self.db,'secret-bill-c',303)[0].id,2002)

    def test_user_sees_only_their_notifications_when_still_joined(self):
        result=inbox.messages(offset=0,unread=False,identity=(self.db.get(User,202),None),db=self.db)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['rows'][0]['title'],'Bank balance: sensitive')
        self.assertTrue(result['rows'][0]['can_open'])
        self.assertNotIn('Other account secret',str(result))

    def test_removed_user_inbox_redacts_past_bill_details(self):
        self.db.get(SplitBillParticipant,22).status='removed';self.db.commit()
        result=inbox.messages(offset=0,unread=False,identity=(self.db.get(User,202),None),db=self.db)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['rows'][0]['title'],'Previous bill activity')
        self.assertFalse(result['rows'][0]['can_open'])
        self.assertNotIn('123.45',str(result))
        self.assertNotIn('Bank balance',str(result))

    def test_inbox_target_rejects_a_bill_without_joined_membership(self):
        self.assertEqual(inbox.destination(self.db,202,'/bill/secret-bill-a'),'/bill/secret-bill-a')
        self.assertIsNone(inbox.destination(self.db,202,'/bill/secret-bill-c'))
        self.assertIsNone(inbox.destination(self.db,202,'https://other.example/private'))

    def test_document_access_allows_managed_case_folder_only(self):
        folder=self.storage/'case_111';folder.mkdir()
        f=folder/'original.jpg';f.write_bytes(b'test image')
        doc=Document(case_id=111,path=str(f),stored_filename='original.jpg')
        self.assertEqual(resolve_document_path(doc),f.resolve())

    def test_document_access_refuses_absolute_path_outside_storage(self):
        secret=Path(self.temp.name)/'private.txt';secret.write_text('private')
        doc=Document(case_id=111,path=str(secret),stored_filename='private.txt')
        self.assertIsNone(resolve_document_path(doc))

    def test_document_access_refuses_symlink_escape(self):
        secret=Path(self.temp.name)/'outside.pdf';secret.write_bytes(b'private')
        folder=self.storage/'case_111';folder.mkdir()
        alias=folder/'alias.pdf'
        try:
            alias.symlink_to(secret)
        except OSError as exc:
            # Windows requires symlink privileges unless Developer Mode permits it.
            # Do not hide other filesystem errors or skip on platforms with symlinks.
            if getattr(exc, 'winerror', None) == 1314:
                self.skipTest('Windows denied symlink creation (WinError 1314); run this test in Linux CI')
            raise
        doc=Document(case_id=111,path=str(alias),stored_filename='alias.pdf')
        self.assertIsNone(resolve_document_path(doc))

    def test_document_access_refuses_wrong_case_and_traversal(self):
        folder=self.storage/'case_222';folder.mkdir()
        f=folder/'other.jpg';f.write_bytes(b'other')
        self.assertIsNone(resolve_document_path(Document(case_id=111,path=str(f),stored_filename='other.jpg')))
        self.assertIsNone(resolve_document_path(Document(case_id=111,path='',stored_filename='../outside.pdf')))

    def test_document_access_refuses_cloud_and_browser_local_paths(self):
        for value in ('s3://bucket/users/101/receipts/test.jpg','local://original.jpg'):
            self.assertIsNone(resolve_document_path(Document(case_id=111,path=value,stored_filename='test.jpg')))

    def make_request(self, method='GET', uid_header=None, csrf=None):
        headers=[(b'cookie',b'pruvs_session=test-session-secret')]
        if uid_header is not None:
            headers.append((b'x-pruvs-user',str(uid_header).encode()))
        if csrf is not None:
            headers.append((b'x-csrf-token',str(csrf).encode()))
        return Request({'type':'http','method':method,'path':'/api/v1/me',
                        'headers':headers,'query_string':b'',
                        'scheme':'https','server':('pruvs.io',443),'client':('127.0.0.1',1234)})

    def make_session(self):
        self.db.add(ReactSession(token_hash=digest('test-session-secret'),
                                 csrf_hash=digest('test-csrf'),user_id=202,
                                 expires_at=self.now+timedelta(days=1)))
        self.db.commit()

    def test_session_cookie_binds_read_request_to_its_real_account(self):
        self.make_session()
        user,session=current(self.make_request(),self.db)
        self.assertEqual(user.id,202)
        self.assertEqual(session.user_id,202)

    def test_cross_tab_user_forgery_and_missing_csrf_are_blocked(self):
        self.make_session()
        cases=[('test-csrf','303',409),('',202,403),('not-the-token',202,403)]
        for csrf, user_header,expected in cases:
            with self.assertRaises(HTTPException) as raised:
                current(self.make_request('POST',uid_header=user_header,csrf=csrf),self.db)
            self.assertEqual(raised.exception.status_code,expected)
        self.assertEqual(current(self.make_request('POST',uid_header=202,csrf='test-csrf'),self.db)[0].id,202)

    def test_blocked_user_cannot_reuse_existing_session(self):
        self.make_session()
        self.db.get(User,202).status='blocked'
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            current(self.make_request(),self.db)
        self.assertEqual(raised.exception.status_code,401)

    def test_admin_role_cannot_be_forged_by_user_id(self):
        with self.assertRaises(HTTPException) as raised:
            admin(identity=(self.db.get(User,202),None))
        self.assertEqual(raised.exception.status_code,403)
        self.assertEqual(admin(identity=(self.db.get(User,404),None))[0].id,404)

    def test_admin_document_download_is_audited(self):
        folder=self.storage/'case_111';folder.mkdir()
        f=folder/'owned.jpg';f.write_bytes(b'test image')
        self.db.add(Document(id=301,case_id=111,path=str(f),stored_filename='owned.jpg'))
        self.db.commit()
        with patch.object(admin_api.d,'add_audit') as log:
            response=admin_api.bill_document(uid=101,cid=111,did=301,
                identity=(self.db.get(User,404),None),db=self.db)
            self.assertEqual(Path(response.path),f.resolve())
            log.assert_called_once_with(self.db,404,'react','export','documents',301,['original_file'])

    def load_react_api(self):
        """Import the actual API functions without starting an OCR provider."""
        provider=types.ModuleType('app.services.standalone_app_service')
        provider._parse_ocr_metadata=lambda row: {}
        label=types.ModuleType('app.react_app.receipt_labels')
        label.receipt_label=lambda db,case_id:'Test Merchant'
        with patch.dict(sys.modules, {'app.services.standalone_app_service':provider,
                                      'app.react_app.receipt_labels':label}):
            spec=importlib.util.spec_from_file_location(
                'app.react_app._security_test_api',
                Path(__file__).resolve().parents[1]/'app/react_app/api.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_api_bill_route_denies_foreign_member(self):
        api=self.load_react_api()
        with self.assertRaises(HTTPException) as raised:
            api.member(self.db,'secret-bill-a',303)
        self.assertEqual(raised.exception.status_code,404)

    def test_api_join_refuses_expired_invitation(self):
        api=self.load_react_api()
        with self.assertRaises(HTTPException) as raised:
            api.join('secret-bill-c',identity=(self.db.get(User,202),None),db=self.db)
        self.assertEqual(raised.exception.status_code,404)
        self.assertIsNone(joined_member(self.db,2002,202))

    def test_api_invitation_refuses_expired_link_to_nonmember(self):
        api=self.load_react_api()
        label=types.ModuleType('app.react_app.receipt_labels')
        label.receipt_label=lambda db,case_id:'Test Merchant'
        with patch.dict(sys.modules,{'app.react_app.receipt_labels':label}):
            with self.assertRaises(HTTPException) as raised:
                api.invitation('secret-bill-c',identity=(self.db.get(User,202),None),db=self.db)
            self.assertEqual(raised.exception.status_code,404)
            preview=api.invitation('secret-bill-c',identity=(self.db.get(User,303),None),db=self.db)
            self.assertEqual(preview['owner'],'Stranger C')
            self.assertTrue(preview['joined'])

    def test_api_owned_case_rejects_foreign_receipt_id(self):
        api=self.load_react_api()
        with self.assertRaises(HTTPException) as raised:
            api.owned_case(self.db,222,101)
        self.assertEqual(raised.exception.status_code,404)
        self.assertEqual(api.owned_case(self.db,111,101).id,111)

    def test_admin_document_download_does_not_expose_foreign_cases(self):
        folder=self.storage/'case_222';folder.mkdir()
        f=folder/'private.jpg';f.write_bytes(b'private')
        self.db.add(Document(id=302,case_id=222,path=str(f),stored_filename='private.jpg'))
        self.db.commit()
        with patch.object(admin_api.d,'add_audit') as log:
            with self.assertRaises(HTTPException) as raised:
                admin_api.bill_document(uid=101,cid=111,did=302,
                    identity=(self.db.get(User,404),None),db=self.db)
            self.assertEqual(raised.exception.status_code,404)
            log.assert_not_called()


if __name__=='__main__':
    unittest.main()
