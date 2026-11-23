# Pruvs Core — Six-provider login setup (3 × 2)

**Status:** UI ready for review; OAuth provider backends are **NOT implemented** in this branch. This must not be deployed or advertised as six working login methods. The existing email/password and optional passkey login remain operational. This is **Core consumer** login, not the separate Business merchant login.

## Login methods

| Tile | Current status | Identity product |
| --- | --- | --- |
| Email | Works today | Existing Pruvs email/password authentication |
| Google | Disabled pending backend + credentials | Google OAuth 2.0 / OpenID Connect |
| Yahoo | Disabled pending backend + credentials | Yahoo OpenID Connect |
| Facebook | Disabled pending backend + credentials | Meta Facebook Login |
| Instagram | Disabled — *not supported for personal consumer accounts* | Meta Instagram API with Instagram Login is intended for **professional** accounts; evaluate and exclude or substitute for consumer login |
| TikTok | Disabled pending backend + credentials | TikTok Login Kit for Web |
| Passkey | Existing separate button (not one of the six tiles) | WebAuthn, if enabled |

The UI intentionally does **not** activate social methods based merely on the presence of environment variables. Once a real backend exists, `/api/v1/config` must return `social_login_providers` with `true` **only after** that provider's start and callback endpoints, identity checks, approved app settings, and database migrations are working.

## Provider dashboards and required credentials

Create separate OAuth applications for staging and production, or register their redirect URIs separately. Do not commit secrets.

- **Google**: [Google Cloud Console](https://console.cloud.google.com/apis/credentials); create a Web application OAuth client. Store `PRUVS_OAUTH_GOOGLE_CLIENT_ID` and `PRUVS_OAUTH_GOOGLE_CLIENT_SECRET` in Render, after backend implementation.
- **Yahoo**: [Yahoo Developer](https://developer.yahoo.com/); create an OpenID Connect application. Store `PRUVS_OAUTH_YAHOO_CLIENT_ID` and `PRUVS_OAUTH_YAHOO_CLIENT_SECRET`.
- **Facebook**: [Meta for Developers](https://developers.facebook.com/apps/); configure Facebook Login and approved redirect URI. Store `PRUVS_OAUTH_FACEBOOK_CLIENT_ID` and `PRUVS_OAUTH_FACEBOOK_CLIENT_SECRET`. App review, live mode, scopes and business verification may be required.
- **Instagram**: [Meta Instagram API](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/); professional-account integration is **not equivalent** to general-purpose personal Instagram sign-in. Do not ship a consumer login option claiming otherwise.
- **TikTok**: [TikTok for Developers](https://developers.tiktok.com/); configure Login Kit for Web and app review. Store `PRUVS_OAUTH_TIKTOK_CLIENT_KEY` and `PRUVS_OAUTH_TIKTOK_CLIENT_SECRET`. TikTok often supplies a stable open_id and profile, **not** a verified email address.
- **Email**: Existing Pruvs authentication and email verification remain as-is; use the existing email transport configuration.
- **Passkey**: Existing server-managed WebAuthn configuration remains separate.

Proposed production callback URLs (these are **not live endpoints yet**):

- `https://pruvs.io/api/v1/auth/social/google/callback`
- `https://pruvs.io/api/v1/auth/social/yahoo/callback`
- `https://pruvs.io/api/v1/auth/social/facebook/callback`
- `https://pruvs.io/api/v1/auth/social/tiktok/callback`

Use the corresponding staging hostname and exactly matching redirect URI. Do **not** register these until the implementation uses these exact paths. Actual callbacks must be registered in provider dashboards and strictly validated server-side.

## Required backend acceptance criteria before enabling any tile

1. Implement `GET /api/v1/auth/social/{provider}/start` and matching callback with authorization-code flow, server-side token exchange, HTTPS-only exact redirect URIs, CSRF-bound **state** with replay protection, expiration, and PKCE where supported/required.
2. Verify issuer, audience, expiry, signature and nonce for OIDC ID tokens, or validate a provider's authenticated userinfo response; never trust client-provided email or profile identifiers.
3. Add a separately migrated `social_identities` table, unique on `(provider, subject)`, referencing Pruvs user IDs. Never auto-link by matching email; require an authenticated user plus reauthentication and explicit linking.
4. For first-time registration, require Terms/Privacy consent, the Core's phone/username requirements, and an independently verified email when the provider does not assert one. Provision only the Core account, never a Business merchant automatically.
5. Handle accounts already linked to another person; provider revocation; changed emails; missing Facebook email; TikTok's missing email; cancellation; denied permissions; expired/reused state; login and account-linking failure messages.
6. Persist only the minimum necessary provider identity data; never log access tokens or passwords. Enforce throttling, no open redirect, audit trails, account disconnect/recovery, and admin controls.
7. Expose a server-side, feature-flagged provider readiness list via `/api/v1/config` only after each backend passes integration tests; default to disabled on staging and production.
8. Test mobile Chrome, Android, iOS Safari, logged-in/out states, account creation, invitation `next` redirects, OAuth cancellation and account collisions; deploy to staging before production.

## Layout & release

Grid is exactly **three columns × two rows** on desktop and mobile: Email, Google, Yahoo / Facebook, Instagram, TikTok. It loads with logo graphics, disabled-provider appearance, keyboard focus styles and screen-reader labels. Passkey remains its own working action below the original form. No changes were made to Business merchant enrollment, databases, production Render configuration, or API credentials.
