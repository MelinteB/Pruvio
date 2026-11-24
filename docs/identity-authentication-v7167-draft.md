# Core 7.1.67 Identity & Authentication — draft, not release-ready

Base: staging b788a057. Business unchanged. This changes the existing staging social identity foundation only. Do not merge to main or deploy until CI and security review succeed.

## Environment contract
GOOGLE, LINKEDIN, YAHOO, FACEBOOK: <PROVIDER>_ENABLED, <PROVIDER>_CLIENT_ID, <PROVIDER>_CLIENT_SECRET. TikTok uses TIKTOK_CLIENT_KEY instead of CLIENT_ID. Flags default off. Apple and Instagram are excluded from Core. Keep credentials private. Use separate sandbox and production credentials. Existing state signing secret is retained; absent that, a domain-separated key is derived from configured provider secrets. Rotation can invalidate pending sign-in flows.

## Remaining release gates
- Reconcile staging vs main (entry points, migrations, schema and existing account/session behavior).
- Verify OIDC nonce behavior, issuer/audience/JWKS and optional email handling with real LinkedIn/Yahoo sandbox accounts. Do not relax token validation to fix an upstream mismatch.
- Verify Facebook token app and subject binding, TikTok subject binding, OTP and callback replay in sandbox. Confirm Facebook app review and TikTok review before public activation.
- Verify OTP challenge ownership and atomic account activation/linking; existing OTP-assisted registration still requires a password. Passwordless social enrollment and direct passkey signup are not implemented in this draft.
- Build six-tile design with direct passkey enrollment, recovery and last-method guards; verify iOS Safari/PWA separately.
- Public data deletion instructions and signed Meta deauthorization/data deletion flows; verify privacy contact/legal information.
- Test every provider, cancel/error path, account collisions, unlinking, invite continuation, existing receipt access and Business regressions.
- Record real TikTok sandbox demo with matching domain, submit review, wait for approval.
- Assign version 7.1.67 only after acceptance; preserve Business version. Do not deploy until credentials and gates reviewed.

Official references: https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2 ; https://developer.yahoo.com/oauth2/guide/openid_connect/ ; https://developers.facebook.com/docs/graph-api/reference/debug_token/ ; https://developers.tiktok.com/docs/en/login-kit-web ; https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info/
