"""Run with: python -m unittest discover -s tests -p test_production_foundation_v7_1_17.py"""
import os
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.reliability import RELEASE, bounded_seconds, frontend_is_ready, require_postgres_if_enabled

class ProductionFoundationTests(unittest.TestCase):
    def test_release(self):
        self.assertEqual(RELEASE, '7.1.37')

    def test_live_interval_bounds(self):
        with patch.dict(os.environ, {'PRUVS_LIVE_ACTIVE_SECONDS': '0.1'}):
            self.assertEqual(bounded_seconds('PRUVS_LIVE_ACTIVE_SECONDS', 5, 2, 15), 5)
        with patch.dict(os.environ, {'PRUVS_LIVE_ACTIVE_SECONDS': '7.5'}):
            self.assertEqual(bounded_seconds('PRUVS_LIVE_ACTIVE_SECONDS', 5, 2, 15), 7.5)
        with patch.dict(os.environ, {'PRUVS_LIVE_ACTIVE_SECONDS': 'NaN'}):
            self.assertEqual(bounded_seconds('PRUVS_LIVE_ACTIVE_SECONDS', 5, 2, 15), 5)

    def test_postgres_guard_is_opt_in(self):
        with patch.dict(os.environ, {'PRUVS_REQUIRE_POSTGRES': 'false'}):
            require_postgres_if_enabled('sqlite:///./pruvio.db')
        with patch.dict(os.environ, {'PRUVS_REQUIRE_POSTGRES': 'true'}):
            with self.assertRaises(RuntimeError):
                require_postgres_if_enabled('sqlite:///./pruvio.db')
            require_postgres_if_enabled('postgresql://localhost/pruvs')

    def test_frontend_ready(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            self.assertFalse(frontend_is_ready(directory))
            (directory / 'index.html').write_text('<html></html>')
            assets = directory / 'assets'
            assets.mkdir()
            (assets / 'app.js').write_text('')
            self.assertFalse(frontend_is_ready(directory))
            (assets / 'app.css').write_text('')
            self.assertFalse(frontend_is_ready(directory))
            (directory / 'index.html').write_text('<script src="/assets/app.js"></script><link href="/assets/app.css">')
            manifests = {
                'version': '7.1.37',
                'assets': {
                    'dist/assets/app.js': hashlib.sha256(b'').hexdigest(),
                    'dist/assets/app.css': hashlib.sha256(b'').hexdigest(),
                },
            }
            (directory / 'build-manifest.json').write_text(json.dumps(manifests))
            self.assertTrue(frontend_is_ready(directory))

if __name__ == '__main__':
    unittest.main()
