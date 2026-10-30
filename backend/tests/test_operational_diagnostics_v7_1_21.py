"""v7.1.37 operational diagnostics regression tests: no DB/network required."""
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.operations import new_request_id, safe_route_template, slow_threshold_ms, should_log, safe_method
from app.reliability import RELEASE

ROOT = Path(__file__).resolve().parents[1]

class OperationalDiagnosticsTests(unittest.TestCase):
    def test_release_and_build_alignment(self):
        self.assertEqual(RELEASE, '7.1.37')
        stamp=(ROOT/'frontend/scripts/stamp-build.mjs').read_text(encoding='utf8')
        self.assertIn("version:'7.1.37'",stamp)
        self.assertIn('pruvs-shell-v7.1.37', (ROOT/'app/static/react-service-worker.js').read_text())
        self.assertIn("CLIENT_RELEASE = '7.1.37'", (ROOT/'frontend/src/professional/ReleaseUpdateBanner.jsx').read_text())

    def test_correlation_id_random_and_header_safety(self):
        a,b=new_request_id(),new_request_id()
        self.assertRegex(a,r'^[0-9a-f]{24}$')
        self.assertNotEqual(a,b)
        app=(ROOT/'app/react_main.py').read_text()
        self.assertIn("response.headers['X-Pruvs-Request-ID']",app)
        self.assertIn('safe_route_template(request.scope)',app)

    def test_only_templates_are_logged(self):
        scope={'route': SimpleNamespace(path='/api/v1/bill/{token}')}
        self.assertEqual(safe_route_template(scope),'/api/v1/bill/{token}')
        self.assertEqual(safe_route_template({'path':'/api/v1/bill/private-token'}),'<unmatched>')
        self.assertEqual(safe_route_template({'route':SimpleNamespace(path='/x/<secret>')}),'<unmatched>')
        self.assertEqual(safe_route_template({}),'<unmatched>')

    def test_threshold_bounds_and_slow_request(self):
        self.assertEqual(slow_threshold_ms({'PRUVS_SLOW_REQUEST_MS':'2500'}),2500)
        self.assertEqual(slow_threshold_ms({'PRUVS_SLOW_REQUEST_MS':'0'}),1500)
        self.assertEqual(slow_threshold_ms({'PRUVS_SLOW_REQUEST_MS':'abc'}),1500)
        self.assertFalse(should_log(200,800,1500))
        self.assertTrue(should_log(200,1600,1500))
        self.assertTrue(should_log(503,10,1500))
        self.assertEqual(safe_method('PATCH'),'PATCH')
        self.assertEqual(safe_method('secret'),'OTHER')

    def test_account_is_on_demand_and_no_receipt_access(self):
        component=(ROOT/'frontend/src/professional/SupportDiagnostics.jsx').read_text()
        account=(ROOT/'frontend/src/Account.jsx').read_text()
        self.assertIn('Check app version',component)
        self.assertIn('<SupportDiagnostics/>',account)
        self.assertIn("credentials: 'same-origin'",component)
        self.assertNotIn('localStorage',component)
        self.assertNotIn('indexedDB',component)
        self.assertNotIn('useEffect',component)
        api=(ROOT/'frontend/src/api.js').read_text()
        self.assertIn('export function getLastFailureRequestId()',api)
        self.assertIn("response.headers.get('X-Pruvs-Request-ID')",api)
        self.assertIn("xhr.getResponseHeader('X-Pruvs-Request-ID')",api)

if __name__=='__main__':unittest.main()
