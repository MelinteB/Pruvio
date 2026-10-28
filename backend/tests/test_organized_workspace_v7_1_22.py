"""v7.1.28 organized workspaces — static source regressions, no user data or DB access."""
import pathlib
import unittest
from app.reliability import RELEASE

ROOT=pathlib.Path(__file__).resolve().parents[1]

class OrganizedWorkspaceTests(unittest.TestCase):
    def test_release_alignment(self):
        self.assertEqual(RELEASE,'7.1.28')
        self.assertIn("version:'7.1.28'",(ROOT/'frontend/scripts/stamp-build.mjs').read_text())
        self.assertIn('pruvs-shell-v7.1.28',(ROOT/'app/static/react-service-worker.js').read_text())

    def test_merchant_tree_and_status_views(self):
        source=(ROOT/'frontend/src/Receipts.jsx').read_text()
        for item in ('Receipts','Open','Settled','Archived','groupMerchants','merchant-tree','Manage removed'):
            self.assertIn(item,source)
        self.assertIn('split_status',source)

    def test_history_server_filters_before_pagination_and_dates(self):
        source=(ROOT/'app/react_app/api.py').read_text()
        self.assertIn('split_status:str|None=None',source)
        self.assertIn("b['status']==split_status",source)
        self.assertIn("'scan_date'",source)
        self.assertIn('case_by_id',source)

    def test_bill_sections_preserve_actions(self):
        source=(ROOT/'frontend/src/Bill.jsx').read_text()
        for item in ('useSearchParams','section===\'items\'','section===\'people\'','id="core-bill-summary"','RoundTable','WhatsApp','act(\'settle\'','act(\'payment\''):
            self.assertIn(item,source)
        self.assertIn('PaymentConfirmation',source)
        self.assertIn('not bank verified', (ROOT/'frontend/src/PaymentConfirmation.jsx').read_text().lower())

    def test_account_admin_keep_advanced_operations(self):
        account=(ROOT/'frontend/src/Account.jsx').read_text()
        admin=(ROOT/'frontend/src/Admin.jsx').read_text()
        self.assertIn('AccountSection',account)
        self.assertIn('SupportDiagnostics',account)
        self.assertIn('Delete account',account)
        self.assertIn('PlanConfiguration',admin)
        self.assertIn('showBilling',admin)
        self.assertIn('Advanced records',admin)

if __name__=='__main__': unittest.main()
