# Pruvs Core — Social identity & signup (staging foundation)

**Date:** 2026-11-23  
**Branch:** `feature/core-social-identity-foundation-20261123`  
**Status:** Draft only. No production settings, database or deployment modified.

## Purpose

Add secure external identity login/sign-up to the Pruvs **Core customer** app,
independent of Pruvs Business merchant accounts. The current Core email/password
login, registration OTP, passkeys and account management remain supported.

## Providers & registration

| Provider | Authentication | First Pruvs registration | Special constraints |
|---|---|---|---|
| Google | OpenID Connect (verified JWT ID token, nonce, PKCE) | Verify provider email and accept terms | Google OAuth app credentials and consent-screen configuration |
| Yahoo | OpenID Connect (verified JWT ID token, nonce) | If verified email claim is absent, use Pruvs email OTP | Yahoo Developer app keys; test Yahoo claims/issuer in staging |
| Facebook | Facebook Login (server-side code exchange, verified provider ID) | Pruvs email/password registration + email OTP | Facebook app review and permitted scopes |
| Instagram | Instagram API with Instagram Login (verified professional-account ID) | Pruvs email/password registration + email OTP | **Business/Creator only**, not general personal Instagram account login |
| TikTok | TikTok Login Kit web (server-side code exchange, open_id) | Pruvs email/password registration + email OTP | Login Kit app approval and HTTPS redirect URI |

**Never** create or link accounts by an unverified email from a provider.
An already registered Core user must sign in first and link the provider from
**Account → Connected social accounts**, even if the social email is identical.
A newly registered user must accept Pruvs Terms and Privacy and provide required
Pruvs profile fields.

## Scope of this implementation

- Separate SQLAlchemy `pruvs_social_accounts` table (unique provider subject),
  no OAuth access/refresh tokens stored.
- HMAC-signed 10-minute provider flow cookie and 15-minute signup ticket, bound
  to an existing session for account linking. Nonce checked for OIDC.
- Server-side token exchanges, OIDC signature, audience and issuer validation.
- Existing Pruvs session issuance via HttpOnly secure cookies.
- Core login and sign-up buttons show **only enabled and configured providers**.
- Core Account: link/unlink; cannot disconnect last external identity without an
  alternative password/linked identity. Password reset by verified email is retained.
- Core Admin: list provider names/last-used times and revoke individual links,
  with confirmation, audit and session revocation.
- Account deletion and admin anonymization erase social identity subjects.
- Existing Core username/email/password login, passkeys, receipts, bills and
  subscription identifiers remain unchanged.

## Migration: Core database only

Run after backup, against the separate Core PostgreSQL database:
`backend/migrations/c1_social_accounts_20261123.sql`.

Verify:
```sql
SELECT to_regclass('public.pruvs_social_accounts');
SELECT column_name
FROM information_schema.columns
WHERE table_schema='public' AND table_name='pruvs_social_accounts'
ORDER BY ordinal_position;
```

Never run against the Business database. The combined production ASGI entrypoint
does not run sub-application startup migrations.

## Render variables (staging first)

- `PRUVS_SOCIAL_LOGIN_ENABLED=true` (global master switch; defaults false)
- `PRUVS_SOCIAL_AUTH_STATE_SECRET`: independently generated cryptographic secret,
  minimum 32 characters. Never reuse Business JWT or Stripe secrets.
- `PUBLIC_BASE_URL`: exact externally accessible HTTPS origin for this Core app,
  no path, query or trailing slash.
- For each provider, set `PRUVS_SOCIAL_<PROVIDER>_ENABLED=true`,
  `PRUVS_SOCIAL_<PROVIDER>_CLIENT_ID`, and
  `PRUVS_SOCIAL_<PROVIDER>_CLIENT_SECRET`.
- Only enable a provider after its dashboard approval, correct redirect URI,
  and successful staging tests. Leave unconfigured providers OFF.
- Keep the global switch OFF in production until consent, privacy/security
  review, migration, observability and return-to-invite tests pass.

### Exact redirect URIs to register in provider consoles

Substitute `https://<core-staging-origin>` for the actual staging public hostname:

```text
https://<core-staging-origin>/api/v1/auth/social/google/callback
https://<core-staging-origin>/api/v1/auth/social/yahoo/callback
https://<core-staging-origin>/api/v1/auth/social/facebook/callback
https://<core-staging-origin>/api/v1/auth/social/instagram/callback
https://<core-staging-origin>/api/v1/auth/social/tiktok/callback
```

Do not register production URLs for staging testing or mix their credentials.
If Core and Business are on the same Render service, the Core social routes
remain under `/api/v1/auth/social/`, not `/business/`.

## API routes

- `GET /api/v1/auth/social/providers`: configured availability
- `GET /api/v1/auth/social/{provider}/start?mode=login|link`: OAuth redirect
- `GET /api/v1/auth/social/{provider}/callback`: state/token verification
- `GET /api/v1/auth/social/pending`: signup ticket presentation
- `POST /api/v1/auth/social/complete`: verified-email OIDC registration
- `POST /api/v1/auth/social/complete-email`: new-user Pruvs email-OTP completion
- `GET /api/v1/auth/social/accounts`: current user's connections
- `DELETE /api/v1/auth/social/accounts/{provider}`: unlink own provider
- `GET /api/v1/admin/users/{uid}/social`: admin list
- `DELETE /api/v1/admin/users/{uid}/social/{provider}`: audited revoke

## Mandatory tests before merge/deploy

```powershell
# From backend with your Python virtualenv activated
python -m pytest -q tests/test_core_social_auth_security_20261123.py
python -m pytest -q tests/test_platform_production_v7166.py

# From backend/frontend
npm ci
npm run build
npm test -- --run
```

Test with **separate mock identities and a staging Core database**:
- Consent cancellation, denial, expired/replayed state and code, wrong
  OAuth audience, wrong nonce, provider outage, unapproved scopes.
- Google and Yahoo verified email sign-up; missing/unverified email must
  require Pruvs OTP. Facebook/TikTok/Instagram account creation requires
  Pruvs email OTP; no silent linking to an existing account.
- Cross-account linking attempts, duplicate provider subject, email collision,
  last-method unlink, admin revoke, disabled/blocked account login, account
  deletion and Terms/Privacy consent.
- Mobile browsers, Safari/Android, passkey coexistence, invitation return route,
  existing login and password reset, Core/Business separation.
- Check Meta/TikTok app review, Yahoo claims, redirects and actual consent
  responses against current provider dashboards before declaring compatibility.
- Verify exact deployed frontend build, same-origin cookies, callback routing
  and no OAuth tokens in logs or URLs.

## Rollback

Set `PRUVS_SOCIAL_LOGIN_ENABLED=false` (and provider flags false),
roll back application image/commit if necessary, and leave additive database
table in place until a separate reviewed data-retention migration. Existing
password/passkey accounts must continue to work.

## Explicit limitations

- This is a **staging implementation**, not a claim of live provider approval.
  It cannot be usable until each developer console is configured and tested.
- Instagram's API-with-Instagram-Login supports professional accounts only.
  For consumer Instagram accounts, offer Facebook or email login instead.
- Pruvs terms/privacy documents in the current repository are labelled drafts;
  production social registration should not be enabled until approved.
- Multi-identity switching, advanced device-session management, provider
  unlink notifications and reauthentication challenges require further review.
