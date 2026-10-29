"""Scoped v7.1.26 join and subscription navigation wiring regression tests."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'frontend/src'
class JoinSubscriptionNavigationTests(unittest.TestCase):
    def test_guard_preserves_join_intent_only_for_token_routes(self):
        main=(ROOT/'main.jsx').read_text()
        self.assertIn('joinToken = location.pathname.match(',main)
        self.assertIn('`/join/${joinToken}?autojin=1`'.replace('autojin','autojoin'),main)
        self.assertIn("'/login?next=' + encodeURIComponent(next)",main)
        self.assertIn('safeNext(new URLSearchParams(location.search).get("next"))',main)
    def test_join_is_performed_then_opened_after_sign_in(self):
        bill=(ROOT/'Bill.jsx').read_text()
        self.assertIn("params.get('autojoin') === '1'",bill)
        self.assertIn('attemptedAutoJoin.current = true',bill)
        self.assertIn("await send('/bills/' + encodeURIComponent(token) + '/join')",bill)
        self.assertIn("nav('/bill/' + encodeURIComponent(token), { replace: true })",bill)
        self.assertIn('onClick={enterBill}',bill)
    def test_auth_and_registration_preserve_requested_destination(self):
        auth=(ROOT/'Auth.jsx').read_text()
        notifications=(ROOT/'Notifications.jsx').read_text()
        self.assertIn("const returnTo = params.get('next') || pending?.next",auth)
        self.assertIn('const invited = invitedBillDestination(returnTo)',auth)
        self.assertIn("sessionStorage.removeItem('pruvs-next')",auth)
        self.assertIn("safeNext(sessionStorage.getItem('pruvs-next'))",notifications)
    def test_free_badge_opens_a_dedicated_subscription_page(self):
        main=(ROOT/'main.jsx').read_text()
        self.assertIn('to="/subscription" className={"membership-plan-badge',main)
        self.assertIn('<Route path="/subscription"',main)
        self.assertIn('<Membership />',main)
    def test_account_legacy_membership_deep_link_remains_available(self):
        account=(ROOT/'Account.jsx').read_text()
        self.assertIn("location.hash==='#membership'",account)
        self.assertIn('React.useEffect(()=>{if(targeted)setOpen(true)}',[account][0])
if __name__=='__main__': unittest.main()
