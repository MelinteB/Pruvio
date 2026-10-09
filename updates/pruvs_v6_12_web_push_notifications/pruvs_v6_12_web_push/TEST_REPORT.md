# Validation — Pruvs v6.12.0

Validated against the available v6.6 full source plus the relevant v6.7–v6.11.1 updates. The installer checks exact source anchors on the user's actual checkout before making changes.

- 19 Python tests passed: authenticated notification API, cross-account restrictions, endpoint validation, logout revocation, test expiry/replay/rate limit, multiple devices, retry persistence, dead subscriptions, email fallback, preference enforcement, future queue eligibility, receipt success/failure hooks, settlement/reopen/reminder hooks.
- Full reconstructed FastAPI/NiceGUI application imports and starts successfully.
- Python compilation and JavaScript syntax checks passed.
- Three browser-DOM simulations passed: iPhone Home Screen guidance, direct-click permission request and test sending, and click confirmation with fragment removal.
- Installer compatibility, first installation, re-check, and repeated installation passed; repeat installation reports no changes.
- Generated VAPID private key was successfully parsed by the installed VAPID library.

No production account was changed, no production notification/email was sent, and no deployment was performed. Real device push delivery, native iPhone permission prompts and lock-screen appearance require the post-deployment tests in README.md. A full browser rendering check was unavailable because the Chromium download failed in this environment.

The update is prepared for deployment, with these real-device acceptance checks outstanding.
