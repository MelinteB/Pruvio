"""Source-level protections for v7.1.38 receipt layout and unchanged split actions."""
from pathlib import Path
import unittest
from app.reliability import RELEASE

ROOT=Path(__file__).resolve().parents[1]


class CompactReceiptTests(unittest.TestCase):
    def test_version_and_build_alignment(self):
        self.assertEqual(RELEASE,'7.1.38')
        self.assertIn("version:'7.1.38'", (ROOT/'frontend/scripts/stamp-build.mjs').read_text())
        self.assertIn('pruvs-shell-v7.1.38', (ROOT/'app/static/react-service-worker.js').read_text())

    def test_receipt_uses_paper_component_and_keeps_split_unchanged(self):
        src=(ROOT/'frontend/src/Receipts.jsx').read_text()
        self.assertIn('<ReceiptPaper receipt={r}',src)
        self.assertNotIn('<div className="stats"><Panel><span>{t("Receipt total")}',src)
        self.assertIn("await send('/receipts/' + id + '/split'",src)
        self.assertIn('nav(\'/bill/\' + s.token)',src)
        paper=(ROOT/'frontend/src/ReceiptPaper.jsx').read_text()
        self.assertIn('aria-label={t(\'Receipt items\')}',paper)
        self.assertIn('<table className="pruvs-thermal-items">',paper)
        self.assertIn('item.total_price',paper)
        self.assertIn('receipt?.receipt_total',paper)
        self.assertNotIn('send(',paper)

    def test_compact_spacing_preserves_allocation_and_touch_controls(self):
        css=(ROOT/'frontend/src/receipt-paper.css').read_text()
        self.assertIn('max-width: 535px',css)
        self.assertIn('.pruvs-thermal-items td',css)
        self.assertIn('min-width: 40px; min-height: 40px',css)
        self.assertIn('.v22-bill-layout #core-bill-items .item',css)
        self.assertIn("import './receipt-paper.css'",(ROOT/'frontend/src/main.jsx').read_text())
        self.assertIn('--item-share-background',(ROOT/'frontend/src/participant-colors.css').read_text())

    def test_ro_translation_of_new_labels(self):
        text=(ROOT/'frontend/src/i18n.js').read_text(encoding='utf-8')
        self.assertIn("'Extracted from receipt · check against the original'",text)
        self.assertIn("'Item': 'Articol'",text)
        self.assertIn("'Amount': 'Valoare'",text)

if __name__=='__main__': unittest.main()
