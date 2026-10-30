"""v7.1.35 sticky bill overview and inline allocation summary source regressions."""
import unittest
from pathlib import Path
from app.reliability import RELEASE

ROOT=Path(__file__).resolve().parents[1]

class FloatingBillWorkspaceTests(unittest.TestCase):
    def test_release_alignment(self):
        self.assertEqual(RELEASE,'7.1.35')
        self.assertIn("version:'7.1.35'",(ROOT/'frontend/scripts/stamp-build.mjs').read_text())
        self.assertIn('pruvs-shell-v7.1.35',(ROOT/'app/static/react-service-worker.js').read_text())
    def test_overview_stays_on_screen(self):
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        css=(ROOT/'frontend/src/floating-bill-workspace.css').read_text()
        self.assertIn('pruvs-floating-bill-overview',bill)
        self.assertIn('position: sticky',css)
        self.assertIn('top: 80px',css)
        self.assertIn('top: 65px',css)
        self.assertIn("'./floating-bill-workspace.css'",(ROOT/'frontend/src/main.jsx').read_text())
    def test_summary_follows_item_selection_without_third_view(self):
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        core=(ROOT/'frontend/src/professional/CorePages.jsx').read_text()
        self.assertGreater(bill.index('id="core-bill-summary"'),bill.index('id="core-bill-items"'))
        self.assertNotIn("section==='summary'",bill)
        self.assertIn("requested === 'people' ? 'people' : 'items'",bill)
        self.assertIn("requested !== 'summary'",bill)  # old deep links still scroll to summary
        self.assertIn("['people','People',Users]",core)
        self.assertNotIn("['summary','Summary',FileText]",core)
    def test_blue_allocation_states_and_preservation(self):
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        css=(ROOT/'frontend/src/floating-bill-workspace.css').read_text()
        core=(ROOT/'frontend/src/professional/CorePages.jsx').read_text()
        self.assertIn('itemAllocationState(item, data.my_participant_id)',bill)
        self.assertIn('is-selected-by-me',bill)
        self.assertIn('is-fully-allocated',bill)
        self.assertIn('Fully allocated',bill)
        self.assertIn('Selected by you',bill)
        self.assertIn('Number(a.quantity)',core)
        self.assertIn('.item.is-selected-by-me',css)
        self.assertIn('.item.is-fully-allocated',css)
        self.assertIn('linear-gradient',css)
        self.assertIn('text-decoration-line: line-through',css)
        for action in ("act('settle'", "act('reopen'", "act('payment'", 'onInvite={() => setShare(true)}', 'Currency setup'):
            self.assertIn(action,bill)

if __name__=='__main__':
    unittest.main()
