"""v7.1.20 offline build fingerprint and launch safety checks."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.reliability import (
    RELEASE, frontend_build_report, frontend_is_ready, require_build_match_if_enabled
)


class LaunchReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.frontend = Path(self.temp.name)
        (self.frontend / 'assets').mkdir()
        self.build('7.1.34')

    def build(self, version, javascript=b'console.log("pruvs")', css=b'body{margin:0}'):
        assets = self.frontend / 'assets'
        (assets / 'index-TEST.js').write_bytes(javascript)
        (assets / 'index-TEST.css').write_bytes(css)
        (self.frontend / 'index.html').write_text(
            '<script type="module" src="/assets/index-TEST.js"></script>'
            '<link rel="stylesheet" href="/assets/index-TEST.css">', encoding='utf-8')
        manifest = {
            'version': version,
            'assets': {
                'dist/assets/index-TEST.js': hashlib.sha256(javascript).hexdigest(),
                'dist/assets/index-TEST.css': hashlib.sha256(css).hexdigest(),
            },
        }
        (self.frontend / 'build-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_version_and_build_identifier(self):
        self.assertEqual(RELEASE, '7.1.34')
        status = frontend_build_report(self.frontend, verify_hashes=True)
        self.assertEqual(status['status'], 'ready')
        self.assertEqual(status['build_version'], RELEASE)
        self.assertEqual(len(status['build_id']), 16)
        self.assertEqual(len(status['assets']), 2)
        self.assertTrue(frontend_is_ready(self.frontend))

    def test_mismatched_version_blocks_readiness(self):
        self.build('7.1.19')
        status = frontend_build_report(self.frontend)
        self.assertEqual(status['status'], 'mismatch')
        self.assertIn('version_mismatch', status['checks'])
        self.assertFalse(frontend_is_ready(self.frontend))

    def test_missing_asset_not_masked_by_old_files(self):
        (self.frontend / 'assets/index-TEST.js').unlink()
        (self.frontend / 'assets/old-unused.js').write_text('old')
        status = frontend_build_report(self.frontend)
        self.assertIn('missing_asset', status['checks'])
        self.assertFalse(frontend_is_ready(self.frontend))

    def test_asset_tampering_detected_by_strict_check(self):
        (self.frontend / 'assets/index-TEST.js').write_text('tampered')
        report = frontend_build_report(self.frontend, verify_hashes=True)
        self.assertIn('asset_hash_mismatch', report['checks'])
        self.assertEqual(report['status'], 'mismatch')

    def test_manifest_missing_or_corrupt(self):
        (self.frontend / 'build-manifest.json').write_text('bad json')
        report = frontend_build_report(self.frontend)
        self.assertIn('missing_or_invalid_manifest', report['checks'])
        self.assertEqual(report['status'], 'mismatch')

    def test_unsafe_path_rejected(self):
        (self.frontend / 'index.html').write_text(
            '<script src="/assets/../secrets.js"></script>'
            '<link href="/assets/index-TEST.css">')
        report = frontend_build_report(self.frontend)
        self.assertIn('unsafe_asset_path', report['checks'])
        self.assertEqual(report['status'], 'mismatch')

    def test_opt_in_guard(self):
        self.build('7.1.19')
        with patch.dict(os.environ, {'PRUVS_REQUIRE_BUILD_MATCH': 'false'}):
            require_build_match_if_enabled(self.frontend)
        with patch.dict(os.environ, {'PRUVS_REQUIRE_BUILD_MATCH': 'true'}):
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                require_build_match_if_enabled(self.frontend)
        self.build('7.1.34')
        with patch.dict(os.environ, {'PRUVS_REQUIRE_BUILD_MATCH': 'true'}):
            require_build_match_if_enabled(self.frontend)

    def test_version_and_banner_wiring(self):
        backend = Path(__file__).resolve().parents[1]
        main = (backend / 'frontend/src/main.jsx').read_text(encoding='utf8')
        notice = (backend / 'frontend/src/professional/ReleaseUpdateBanner.jsx').read_text(encoding='utf8')
        worker = (backend / 'app/static/react-service-worker.js').read_text(encoding='utf8')
        self.assertIn('<ReleaseUpdateBanner />', main)
        self.assertIn("CLIENT_RELEASE = '7.1.34'", notice)
        self.assertIn('cache: \'no-store\'', notice)
        self.assertIn('pruvs-shell-v7.1.34', worker)
        self.assertIn('require_build_match_if_enabled(FRONTEND)', (backend / 'app/react_main.py').read_text(encoding='utf8'))


if __name__ == '__main__':
    unittest.main()
