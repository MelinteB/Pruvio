# Staging Google OAuth — short names (24 November 2026)

Production and staging both read **exactly** these names for Google:

```dotenv
GOOGLE_CLIENT_ID=<staging Google Web client ID>
GOOGLE_CLIENT_SECRET=<staging Google Web client secret>
GOOGLE_ENABLED=false
```

Use a separate Google OAuth Web client for staging, with exact callback:
`https://pruvs-core-staging.onrender.com/api/v1/auth/social/google/callback`.
Configure `PUBLIC_BASE_URL=https://pruvs-core-staging.onrender.com`.
Use a staging-only Render environment group linked to `Pruvs-staging`.
Do not link the production Google credentials group to staging.

**No separate state-secret variable is required for Google**: when no
legacy staging social state key exists, the server derives a domain-separated
OAuth HMAC signing key from `GOOGLE_CLIENT_SECRET`. If the existing
`PRUVS_SOCIAL_AUTH_STATE_SECRET` is already set, the staging experiment keeps
it for compatibility with other experimental providers.

`GOOGLE_ENABLED=false` is a hard off-switch. Setting it to true alone is
not sufficient for a usable login: the correct credentials, provider redirect,
and `pruvs_social_accounts` Core DB table must also exist.

Staging deliberately preserves its separate Core/Business databases,
strict runtime schema checks, and staging-specific startup command.
Production and staging share the 3×2 login layout and E.164 phone validation
but are **not the same Git commit**.

Future provider variable convention: `LINKEDIN_CLIENT_ID`,
`LINKEDIN_CLIENT_SECRET`, `LINKEDIN_ENABLED`, and similarly
`YAHOO_*`. These are planned names; do not enable an unimplemented provider.
