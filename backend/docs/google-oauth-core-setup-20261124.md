# Pruvs Core — Google sign-in setup (2026-11-24)

This implementation adds a 3×2 provider picker with **Google, LinkedIn, Yahoo** in
that exact first-row order, followed by Facebook, Instagram, and TikTok.
The **Email** tile is removed, while the normal email/password form and
WebAuthn passkey login remain available.

**Google is the first implemented provider. All other five social providers remain
disabled until separate provider-specific integrations are reviewed.** Do not
set `*_ENABLED=true` until the full checklist below passes.

## 1. Configure a Google Cloud OAuth application

Use [Google Auth Platform](https://console.cloud.google.com/auth/clients).
Create a project and configure Branding (app: **Pruvs**), Audience, authorized
domain **pruvs.io**, home page `https://pruvs.io`, Terms
`https://pruvs.io/terms`, and Privacy `https://pruvs.io/privacy`.
While testing an External app, add specific Google test users.

Create **OAuth Client ID** → **Web application**:

- Application name: `Pruvs Core - production`
- Authorized JavaScript origin (optional for server-side-only OAuth): `https://pruvs.io`
- Authorized redirect URI (exact): `https://pruvs.io/api/v1/auth/social/google/callback`

For staging, use a *separate* Web OAuth client:

- Redirect URI: `https://pruvs-core-staging.onrender.com/api/v1/auth/social/google/callback`
- Origin: `https://pruvs-core-staging.onrender.com`

Store Client ID and Client Secret only in the corresponding Render service's
secret Environment settings; never expose secrets in frontend builds, code,
terminal transcripts sent to ChatGPT, or logs. Only request
`openid email profile` Google identity scopes.

## 2. Apply the Core database migration (NOT Business)

On a reviewed Core-DB migration step, apply
`backend/migrations/c1_social_accounts_20261124.sql` to **DATABASE_URL**.
Do **not** apply to BUSINESS_DATABASE_URL.
Unique constraints on `(provider,subject)` and `(user_id,provider)`
prevent duplicate or conflicting provider links.

Before activation, `GET /api/v1/auth/social/providers` should report
`google.enabled=false` unless the feature flags, credentials and schema
are all ready.

## 3. Link the Google environment group and configure three keys

Create / keep the Render environment group `PRUVS-PROD-OAUTH-GOOGLE` and
**link it** to the production **Pruvs** web service in Environment settings.
Use **exactly these names**; do not put credentials in source code:

```dotenv
GOOGLE_CLIENT_ID=<Google Web OAuth client ID>
GOOGLE_CLIENT_SECRET=<Google Web OAuth client secret>
GOOGLE_ENABLED=false
```

The Google code now reads these keys directly, matching the environment group.
Google is **disabled by default** until you explicitly change
`GOOGLE_ENABLED=true`. Previous `PRUVS_SOCIAL_*` Google names are not used.
`PRUVS_SOCIAL_LOGIN_ENABLED` is not required for Google.

**No fourth Google secret is needed:** the backend derives a domain-separated
OAuth state-cookie signing key from `GOOGLE_CLIENT_SECRET` with HMAC-SHA256.
Rotating the client secret invalidates unexpired OAuth state tickets and
onboarding cookies. Keep the secret private and never paste it into chat.

Keep `PUBLIC_BASE_URL=https://pruvs.io` on production (or use the documented
production default). The exact Google Cloud callback remains:
`https://pruvs.io/api/v1/auth/social/google/callback`.

For staging, use a **separate Google OAuth client**, and the same three short
names in the staging service (prefer a distinct `PRUVS-STAGE-OAUTH-GOOGLE`
environment group), with `PUBLIC_BASE_URL` set to the staging hostname.
Never attach production credentials to staging.

Keep `GOOGLE_ENABLED=false` until Google Cloud redirect setup,
the social-account table, and staging callback tests have succeeded. Avoid
rotating unrelated Resend, Core DB, or Business credentials.

**Future provider naming:** use concise provider prefixes such as
`LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_ENABLED`,
and `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_ENABLED`.
These **are conventions, not implemented provider configurations**.

## 4. Acceptance tests before production activation

1. Visit `/login`: tiles order is Google / LinkedIn / Yahoo then
   Facebook / Instagram / TikTok, all below the normal Sign in button.
2. Google tile is disabled while server config is incomplete; the other five
   never become enabled by Google credentials.
3. Google authorize flow redirects through Google's HTTPS endpoint and
   validates state, PKCE, Google RSA signature, audience, issuer, token expiry,
   nonce and `email_verified`.
4. New Google user → `/register?social=pending`: name and verified email
   prefilled; mandatory country selector + phone; username derived/editable;
   Terms/Privacy required; no new password needed; normalized E.164 saved.
   Account is created only after completing this profile.
5. Sign out and sign in again with the same Google account; no repeated
   onboarding; existing receipts and account ID persist.
6. Existing email/password account with identical email **must not** be
   automatically claimed by Google. Sign into Pruvs normally, open
   **Account → Account security → Google account sign-in → Connect Google**,
   and perform Google consent. Then a normal Google sign-in uses that
   existing Pruvs user and its history.
7. Invalid phone lengths, mismatched country prefixes, missing consent, an
   already registered phone, duplicate provider identity, cancelled OAuth,
   tampered state and expired tickets fail safely.
8. Confirm that `/business` merchant signup and login, Core email/password,
   passkeys, and sharing still work.

Phone formatting is **not phone ownership verification**.
`is_phone_verified` remains false until an independent SMS verification
channel is implemented. Never treat a phone number alone as an authentication
or recovery secret.

## Release gate

- CI: `.github/workflows/verify-core-google-oauth.yml`
- PR: `feature/core-google-oauth-linkedin-second-20261124`
- All OAuth provider flags remain off by default. A code deployment alone
  does not make Google usable until Google Cloud credentials and schema
  are configured and verified with an actual OAuth callback.
