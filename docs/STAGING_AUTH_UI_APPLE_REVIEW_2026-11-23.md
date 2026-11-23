# Staging UI and authentication audit — 2026-11-23

## Reported issues (from actual merchant screenshot and Core app review)

1. **Business navigation:** The dark green aside ended above the `Account` group, causing `Team & security`, the environment chip and Logout to render on a pale page background with illegible text. The sidebar used `height:100vh` without its own desktop scroll, while menu content was longer than a short viewport.
2. **Core sign-in/registration:** The component rendered social buttons only for providers with `enabled=true`. All OAuth providers currently require developer credentials/app approval, so their entire UI disappeared. In addition, the initial draft did not include Apple sign-in.
3. **Inconsistent translation:** `Account` and `Team & security` were not translated in the Romanian Business locale.

## Implemented, staging only

- A full-height, independently scrollable sidebar with a consistent dark background on desktop and mobile, footer within the sidebar, and readable account buttons.
- More usable responsive `Team & security` forms and role controls; Romanian navigation/action translations.
- Clearly visible provider choices at the **top** of Core login and signup, plus the Account connection section, with a true `Setup required / Unavailable` status rather than a dead link.
- Core provider choices: Google, Apple, Facebook, Yahoo, TikTok; Instagram Professional can be linked from Account and used to sign into a previously linked profile (not personal Instagram).
- Apple web OAuth/OIDC: Services ID, signed ES256 developer client-secret JWT derived from an encrypted Render env secret, Apple JWKS token verification, issuer/audience/nonce checks, browser-bound HMAC state, secure form POST callback and same-origin GET bridge before account linking.
- Privacy: no Apple/Google/Facebook refresh or access tokens stored; provider subjects remain internal. No automatic account linking by email.
- Existing email, password, passkeys, administrator controls, account linking and staged social SQL migration retained.

## Activation requirements

No external identity is usable without the provider's approved credentials. By default
`PRUVS_SOCIAL_LOGIN_ENABLED=false` and individual provider flags are false.
The frontend now **shows** the choices for discoverability, but labels them unavailable
until their exact configuration is present.

Required for each of Google, Yahoo, Facebook and TikTok:
`PRUVS_SOCIAL_<PROVIDER>_CLIENT_ID`, `PRUVS_SOCIAL_<PROVIDER>_CLIENT_SECRET`,
`PRUVS_SOCIAL_<PROVIDER>_ENABLED=true` plus the global state secret and flag.

Apple web registration requires an active Apple Developer Program account,
Sign in with Apple enabled for a Services ID, a domain + return URL configured
in Apple Developer, and an Apple private key downloaded by the app owner.
Place the **base64 of the .p8 private-key file** in the Render secret variable
`PRUVS_SOCIAL_APPLE_PRIVATE_KEY_BASE64` (never commit or paste key into a chat).
Also set:
- `PRUVS_SOCIAL_APPLE_CLIENT_ID` = Apple web Services ID
- `PRUVS_SOCIAL_APPLE_TEAM_ID` = Developer team identifier
- `PRUVS_SOCIAL_APPLE_KEY_ID` = Sign in with Apple key identifier
- `PRUVS_SOCIAL_APPLE_ENABLED=true`
- `PRUVS_SOCIAL_AUTH_STATE_SECRET` = separate random secret, >=32 characters
- `PUBLIC_BASE_URL=https://pruvs-core-staging.onrender.com`
- `PRUVS_SOCIAL_LOGIN_ENABLED=true` after all mandatory tests pass

Apple's registered return URL for this staging service:
`https://pruvs-core-staging.onrender.com/api/v1/auth/social/apple/callback`

Other staging provider callback URLs follow:
`https://pruvs-core-staging.onrender.com/api/v1/auth/social/<provider>/callback`.

Apple delivers a cross-site **form POST**; only the transient state cookie is
SameSite=None; the Pruvs session remains SameSite=Lax. The validated provider
subject passes through a 90-second signed, HttpOnly, SameSite=Lax bridge before
connecting to a signed-in account on a same-origin GET.

Verify email relay configuration when testing Apple's private relay email addresses,
and treat name sharing as optional/first-time only.

## QA gate / rollback

- Run `pytest -q backend/tests/test_combined_platform_routes.py` and
  `pytest -q backend/tests/test_core_social_auth_security_20261123.py` with
  appropriate `PYTHONPATH`.
- Run both Vite builds, and verify 360px, 390px, 768px, short 550px viewport
  and desktop navigation; scroll the entire left aside to the account footer.
- Verify Core login and Register pages show all options even when disabled,
  no disabled provider is a clickable link, and the enabled provider redirect
  matches the correct `PUBLIC_BASE_URL`.
- Test Apple against a registered staging Apple Services ID on Safari/iOS,
  Chrome and desktop. Validate malformed POST, stale state, nonce mismatch,
  duplicate identity, account-link cancellation and account logout.
- Do not enable in production until legal, privacy, provider approvals, sign-in
  and account-recovery tests pass. Roll back UI release independently from
  provider flags; no database migration or wipe is required for this change.
