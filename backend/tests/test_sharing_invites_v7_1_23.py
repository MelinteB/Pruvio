"""v7.1.28 sharing & invitations source contracts (no database/network required)."""
import unittest
from pathlib import Path
from app.reliability import RELEASE

ROOT = Path(__file__).resolve().parents[1]


class SharingInvitesTests(unittest.TestCase):
    def test_release_alignment(self):
        self.assertEqual(RELEASE, '7.1.28')
        self.assertIn("version:'7.1.28'", (ROOT/'frontend/scripts/stamp-build.mjs').read_text())
        self.assertIn('pruvs-shell-v7.1.28', (ROOT/'app/static/react-service-worker.js').read_text())
        self.assertIn("CLIENT_RELEASE = '7.1.28'", (ROOT/'frontend/src/professional/ReleaseUpdateBanner.jsx').read_text())

    def test_modal_replaces_inline_share(self):
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        self.assertIn('<InviteDialog open={share}', bill)
        self.assertNotIn('id="core-bill-invite"', bill)
        self.assertIn('onInvite={() => setShare(true)}', bill)

    def test_tree_invite_opens_modal(self):
        receipts=(ROOT/'frontend/src/Receipts.jsx').read_text()
        self.assertIn('setInviteSplit({ token:b.token', receipts)
        self.assertIn('<InviteDialog open={!!inviteSplit}', receipts)
        self.assertIn("b.status==='open'", receipts)

    def test_privacy_constraints(self):
        dialog=(ROOT/'frontend/src/professional/InviteDialog.jsx').read_text()
        self.assertIn('navigator.contacts.select', dialog)
        self.assertIn('multiple: true', dialog)
        self.assertIn('normalizeInvitePhone', dialog)
        self.assertNotIn('WhatsApp group for this bill', dialog)
        self.assertIn('waShareUrl', dialog)
        self.assertNotIn('/users/', dialog)
        self.assertNotIn('/contacts/upload', dialog)

    def test_round_table_has_open_bill_invite(self):
        table=(ROOT/'frontend/src/professional/RoundTable.jsx').read_text()
        self.assertIn("status === 'open'", table)
        self.assertIn('onInvite={onInvite}', table) if 'onInvite={onInvite}' in table else self.assertIn('onClick={onInvite}', table)

if __name__ == '__main__':
    unittest.main()
