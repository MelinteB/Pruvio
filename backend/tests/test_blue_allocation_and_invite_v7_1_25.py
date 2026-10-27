"""v7.1.26 scoped UI regression contract; no DB, external APIs or user data."""
import unittest
from pathlib import Path
from app.reliability import RELEASE

ROOT=Path(__file__).resolve().parents[1]

class BlueAllocationInviteTests(unittest.TestCase):
    def test_release_alignment(self):
        self.assertEqual(RELEASE,'7.1.26')
        self.assertIn("version:'7.1.26'",(ROOT/'frontend/scripts/stamp-build.mjs').read_text())
        self.assertIn('pruvs-shell-v7.1.26',(ROOT/'app/static/react-service-worker.js').read_text())
    def test_blue_gradient_for_selected_and_fully_allocated(self):
        css=(ROOT/'frontend/src/floating-bill-workspace.css').read_text()
        self.assertIn('.item.is-selected-by-me',css)
        self.assertIn('.item.is-fully-allocated',css)
        self.assertIn('linear-gradient',css)
        self.assertIn('border-left: 4px solid #3765f4',css)
        self.assertIn('border-left: 4px solid #204ee0',css)
        self.assertNotIn('#148557',css)
    def test_completed_items_strike_name_not_cost_or_controls(self):
        css=(ROOT/'frontend/src/floating-bill-workspace.css').read_text()
        self.assertIn('> .row:first-child > .grow > strong:first-child',css)
        self.assertIn('text-decoration-line: line-through',css)
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        self.assertIn('is-fully-allocated',bill)
        self.assertIn('Fully allocated',bill)
        self.assertIn('Selected by you',bill)
    def test_group_removed_but_whatsapp_invite_remains(self):
        source=(ROOT/'frontend/src/professional/InviteDialog.jsx').read_text()
        styles=(ROOT/'frontend/src/invite-dialog.css').read_text()
        self.assertNotIn('WhatsApp group for this bill',source)
        self.assertNotIn('whatsappGroupName',source)
        self.assertNotIn('pruvs-invite-group-toggle',styles)
        self.assertIn('waShareUrl',source)
        self.assertIn('normalizeInvitePhone',source)
        self.assertIn('navigator.contacts.select',source)
    def test_payment_and_amount_calculations_unchanged(self):
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        self.assertIn("act('payment'",bill)
        self.assertIn('itemAllocationState(item, data.my_participant_id)',bill)
        self.assertIn('onInvite={() => setShare(true)}',bill)

if __name__=='__main__': unittest.main()
