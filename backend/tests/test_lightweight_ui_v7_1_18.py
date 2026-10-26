"""Offline smoke tests for Pruvs Lightweight UI v7.1.19."""
from pathlib import Path
import unittest

BACKEND = Path(__file__).resolve().parents[1]


class LightweightUIReleaseTests(unittest.TestCase):
    def test_release_version_is_aligned(self):
        self.assertIn('7.1.20', (BACKEND / 'app/reliability.py').read_text(encoding='utf-8'))
        self.assertIn('7.1.20', (BACKEND / 'frontend/scripts/stamp-build.mjs').read_text(encoding='utf-8'))
        self.assertIn('pruvs-shell-v7.1.20', (BACKEND / 'app/static/react-service-worker.js').read_text(encoding='utf-8'))

    def test_lazy_routes_and_loading_state(self):
        source = (BACKEND / 'frontend/src/main.jsx').read_text(encoding='utf-8')
        for item in ['const Admin = lazy(', 'const Auth = lazy(', 'const Bill = lazy(', 'const History = lazy(', 'const Expenses = lazy(', '<Suspense fallback=']:
            with self.subTest(item=item):
                self.assertIn(item, source)

    def test_optimized_brand_assets_and_fallback(self):
        asset_dir = BACKEND / 'app/static'
        for name in ['pruvs-logo.png', 'pruvs-mark.png', 'pruvs-logo-compact.webp', 'pruvs-mark-compact.webp']:
            with self.subTest(name=name):
                self.assertTrue((asset_dir / name).is_file(), name)
        source = (BACKEND / 'frontend/src/main.jsx').read_text(encoding='utf-8')
        self.assertIn('srcSet="/static/pruvs-logo-compact.webp"', source)
        self.assertIn('src="/static/pruvs-logo.png"', source)

    def test_simplified_home_preserves_receipt_entry(self):
        source = (BACKEND / 'frontend/src/Receipts.jsx').read_text(encoding='utf-8')
        self.assertIn('core-summary-strip', source)
        self.assertIn('groups.slice(0, 5)', source)
        self.assertIn('<HomeWelcome user={user}', source)
        self.assertIn('request(\'/history?', source)

if __name__ == '__main__':
    unittest.main()
