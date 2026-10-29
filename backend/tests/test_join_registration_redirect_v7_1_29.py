"""End-to-end invitation return wiring source contract, no account credentials required."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RegistrationJoinTests(unittest.TestCase):
    def test_registration_returns_to_invited_session_first(self):
        auth=(ROOT/'frontend/src/Auth.jsx').read_text()
        self.assertIn('next:safeNext(returnTo)',auth)
        self.assertIn('params.get(\'next\') || pending?.next',auth)
        self.assertIn('const invited = invitedBillDestination(returnTo)',auth)
        self.assertIn('navigate(invited, { replace: true })',auth)
        self.assertIn('navigate(safeNext(returnTo), { replace: true })',auth)
        self.assertLess(auth.index('navigate(invited, { replace: true })'),auth.index('navigate(safeNext(returnTo), { replace: true })'))
    def test_authenticated_register_route_keeps_token(self):
        app=(ROOT/'frontend/src/main.jsx').read_text()
        self.assertIn('invitedBillDestination(new URLSearchParams(location.search).get("next"))',app)
        self.assertIn('path="/join/:token"',app)
        self.assertIn('path="/bill/:token"',app)
    def test_only_local_invitation_routes_are_autojoined(self):
        helper=(ROOT/'frontend/src/join-return.js').read_text()
        self.assertIn('A-Za-z0-9_-',helper)
        self.assertIn('autojoin=1',helper)
        self.assertIn('return null',helper)
    def test_live_join_endpoint_does_not_change(self):
        bill=(ROOT/'frontend/src/Bill.jsx').read_text()
        self.assertIn("await send('/bills/' + encodeURIComponent(token) + '/join')",bill)
        self.assertIn("nav('/bill/' + encodeURIComponent(token), { replace: true })",bill)

if __name__ == '__main__':unittest.main()
