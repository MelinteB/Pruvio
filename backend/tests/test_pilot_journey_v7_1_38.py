"""v7.1.38 pilot: real isolated FastAPI/SQLite request paths and read-only smoke.

No production database, cloud provider, email, OCR API, user credentials or network.
"""
from __future__ import annotations

import importlib
import json
import pkgutil
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
import app.models
for model in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module('app.models.' + model.name)
from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.react_session import ReactSession
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.react_app.api import router as api_router
from app.react_app.inbox import router as inbox_router
from app.react_app.auth import COOKIE, CSRF_COOKIE, digest
from scripts import pilot_smoke


class PilotApiJourneyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.factory()
        self.db.add_all([
            User(id=101, username='pilotowner', username_key='pilotowner', phone_number='+40101010101', status='active', name='Owner'),
            User(id=202, username='pilotmember', username_key='pilotmember', phone_number='+40202020202', status='active', name='Member', preferred_language='ro'),
            User(id=303, username='pilotguest', username_key='pilotguest', phone_number='+40303030303', status='active', name='Guest'),
            Case(id=41, user_id=101, module='receipt', status='processed'),
            Document(id=42, case_id=41, path='local://pilot', stored_filename='pilot.jpg', mime_type='image/jpeg'),
            ReceiptItem(id=43, case_id=41, document_id=42, name='Soup', quantity=2, unit_price=12.5, total_price=25),
            SplitBillSession(id=44, case_id=41, owner_user_id=101, token='pilot-isolated-bill-token', status='open', expected_participants_count=3, expires_at=datetime.utcnow()+timedelta(days=2)),
            SplitBillParticipant(id=45, session_id=44, user_id=101, role='owner', status='joined', display_name='Owner', participant_token='pilot_owner'),
            SplitBillParticipant(id=46, session_id=44, user_id=202, role='participant', status='joined', display_name='Member', participant_token='pilot_member'),
            SplitBillItemAssignment(id=47, session_id=44, participant_id=46, receipt_item_id=43, quantity=1, amount=12.5),
        ])
        for uid in (101, 202, 303):
            self.db.add(ReactSession(token_hash=digest(f'pilot-session-{uid}'), user_id=uid,
                                     csrf_hash=digest(f'pilot-csrf-{uid}'), expires_at=datetime.utcnow()+timedelta(hours=2)))
        self.db.commit()
        app = FastAPI()
        app.include_router(api_router)
        app.include_router(inbox_router)
        def fixture_db():
            yield self.db
        app.dependency_overrides[get_db] = fixture_db
        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def get(self, path, uid=None):
        cookies = {COOKIE: f'pilot-session-{uid}'} if uid else {}
        return self.client.get(path, cookies=cookies)

    def mutate(self, method, path, uid, *, csrf=True, correct_user=True, data=None):
        headers = {'X-Pruvs-User': str(uid if correct_user else 999)}
        if csrf:
            headers['X-CSRF-Token'] = f'pilot-csrf-{uid}'
        return self.client.request(method, path, json=data, headers=headers, cookies={COOKIE: f'pilot-session-{uid}'})

    def test_public_config_version_matches_release(self):
        from app.reliability import RELEASE
        response=self.get('/api/v1/config')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['version'], RELEASE)

    def test_anonymous_cannot_read_account_bill_history_or_inbox(self):
        for path in ('/api/v1/me','/api/v1/history','/api/v1/bills/pilot-isolated-bill-token',
                     '/api/v1/receipts/41','/api/v1/account/delete/preview','/api/v1/inbox'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code,401)

    def test_real_owner_and_member_can_access_the_bill(self):
        for uid in (101,202):
            response=self.get('/api/v1/bills/pilot-isolated-bill-token',uid)
            self.assertEqual(response.status_code,200)
            self.assertIn('participants', response.json())

    def test_uninvited_account_cannot_access_bill(self):
        response=self.get('/api/v1/bills/pilot-isolated-bill-token',303)
        self.assertEqual(response.status_code,404)

    def test_guest_cannot_fetch_owners_receipt(self):
        self.assertEqual(self.get('/api/v1/receipts/41',303).status_code,404)

    def test_cross_tab_user_forgery_is_rejected(self):
        response=self.mutate('DELETE','/api/v1/bills/pilot-isolated-bill-token/participants/46',101,correct_user=False)
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.db.get(SplitBillParticipant,46).status,'joined')

    def test_missing_csrf_is_rejected(self):
        response=self.mutate('DELETE','/api/v1/bills/pilot-isolated-bill-token/participants/46',101,csrf=False)
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.db.get(SplitBillParticipant,46).status,'joined')

    def test_nonowner_cannot_remove_participant(self):
        response=self.mutate('DELETE','/api/v1/bills/pilot-isolated-bill-token/participants/45',202)
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.db.get(SplitBillParticipant,45).status,'joined')

    def test_owner_removes_member_and_revokes_access(self):
        response=self.mutate('DELETE','/api/v1/bills/pilot-isolated-bill-token/participants/46',101)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.db.get(SplitBillParticipant,46).status,'removed')
        self.assertEqual(self.db.query(SplitBillItemAssignment).count(),0)
        self.assertEqual(self.get('/api/v1/bills/pilot-isolated-bill-token',202).status_code,404)
        self.assertEqual(self.get('/api/v1/bills/pilot-isolated-bill-token/invite',202).status_code,404)
        self.assertIn(self.mutate('POST','/api/v1/bills/pilot-isolated-bill-token/join',202).status_code,(403,404))
        self.assertEqual(self.get('/api/v1/bills/pilot-isolated-bill-token',101).status_code,200)

    def test_removal_inbox_is_generic_without_bill_details(self):
        response=self.mutate('DELETE','/api/v1/bills/pilot-isolated-bill-token/participants/46',101)
        self.assertEqual(response.status_code,200)
        inbox=self.get('/api/v1/inbox',202)
        self.assertEqual(inbox.status_code,200)
        rows=inbox.json()['rows']
        self.assertTrue(rows)
        text=json.dumps(rows)
        self.assertNotIn('pilot-isolated-bill-token',text)
        self.assertNotIn('Soup',text)
        self.assertNotIn('12.5',text)

    def test_owner_cannot_remove_self(self):
        response=self.mutate('DELETE','/api/v1/bills/pilot-isolated-bill-token/participants/45',101)
        self.assertEqual(response.status_code,403)

    def test_payment_activity_blocks_removal_and_preserves_allocations(self):
        member=self.db.get(SplitBillParticipant,46)
        member.payment_status='reported'
        self.db.commit()
        response=self.mutate('DELETE','/api/v1/bills/pilot-isolated-bill-token/participants/46',101)
        self.assertEqual(response.status_code,409)
        self.assertEqual(member.status,'joined')
        self.assertEqual(self.db.query(SplitBillItemAssignment).count(),1)


class PilotSmokeTests(unittest.TestCase):
    def fake(self, broken=None):
        def transport(origin, path):
            if path in pilot_smoke.PROTECTED_ROUTES:
                code = 200 if path == broken else 401
                return code, {}, b'{}'
            data = {'/health':{'status':'ok','version':'7.1.38'},
                    '/ready':{'status':'ready','version':'7.1.38'},
                    '/api/v1/release':{'status':'ready','version':'7.1.38','build_id':'a'*16},
                    '/api/v1/config':{'version':'7.1.38'}}[path]
            return 200, {'x-pruvs-release':'7.1.38','cache-control':'no-store','x-content-type-options':'nosniff'}, json.dumps(data).encode('utf-8')
        return transport

    def test_healthy_and_private_endpoints(self):
        checks=pilot_smoke.run_checks('https://pruvs.io',transport=self.fake())
        self.assertTrue(all(ok for _,ok in checks))
        self.assertEqual(len(checks),12)

    def test_private_endpoint_leak_is_caught(self):
        checks=pilot_smoke.run_checks('https://pruvs.io',transport=self.fake('/api/v1/history'))
        self.assertFalse(all(ok for _,ok in checks))

    def test_refuses_external_and_path_urls(self):
        for url in ('http://pruvs.io','https://example.com','https://pruvs.io@evil.example',
                    'https://pruvs.io/foo','https://pruvs.io?token=1',
                    'http://127.0.0.1:8000','https://pruvs.io#frag'):
            with self.subTest(url=url),self.assertRaises(pilot_smoke.SmokeError):
                pilot_smoke.validate_origin(url)

    def test_explicit_localhost_requires_flag(self):
        self.assertEqual(pilot_smoke.validate_origin('http://127.0.0.1:8000',allow_local=True),'http://127.0.0.1:8000')
        with self.assertRaises(pilot_smoke.SmokeError):
            pilot_smoke.validate_origin('http://192.168.1.1:8000',allow_local=True)

    def test_failed_readiness_blocks_smoke(self):
        def bad(origin,path):
            code, headers,body=self.fake()(origin,path)
            if path=='/ready':return 503,headers,b'{"status":"unavailable","version":"7.1.38"}'
            return code,headers,body
        checks=pilot_smoke.run_checks('https://pruvs.io',transport=bad)
        self.assertIn(('Database and frontend are ready',False),checks)

    def test_cli_run_never_requires_secret_or_writes_data(self):
        with patch.object(pilot_smoke,'run_checks',return_value=[('Test',True)]) as check:
            self.assertEqual(pilot_smoke.main(['--url','https://pruvs.io']),0)
            check.assert_called_once()


if __name__=='__main__':unittest.main()
