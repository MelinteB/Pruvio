# Pruvs Business — Account access and recovery (draft)

**Branch:** `feature/business-identity-account-foundation-20261123`  
**Target:** Business application and Business database only. Core database must not be altered.  
**Deployment status:** Not deployed or end-to-end tested. Keep feature flags disabled pending review.

## Implemented in this branch

- Merchant enrollment password policy changes from 20–256 to **15–128 characters**, on both server and browser. Existing passwords still authenticate.
- Merchant password recovery via expiring, one-time, signed email link at `/business/merchant-reset.html`. The secret is in the browser fragment, never an HTTP GET request.
- Merchant password-change endpoint for authenticated users; signed access tokens are bound to the current password hash and invalidated after password changes.
- Owner-only team controls: list users, invite staff or managers, change role, disable access, resend setup link, and read audit history.
- Public recovery responses do not disclose whether an email belongs to a merchant account. Reset attempts and invitations reuse database-persisted hashed rate buckets.
- New staff are inactive until they complete their secure invitation. Disabling a member invalidates existing passwords and outstanding tokens.
- Friendlier frontend message when public merchant enrollment is disabled.

## Required staging prerequisites

1. **Business database**: back up and execute `backend/business_migrations/versions/b13a0623_merchant_accounts.sql` against the Business database. This is additive and idempotent; verify `merchant_signup_rates` and `merchant_staff_actions_v1`.
2. **Render environment:** Set `PRUVS_BUSINESS_PASSWORD_RESET_ENABLED=true`, `PRUVS_BUSINESS_PUBLIC_ORIGIN=https://<exact-staging-host>`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, and existing Business secrets. Do not commit credentials.
3. Configure the verified sender domain and check email delivery to real inboxes, including spam. Never log reset links.
4. The Business Vite build must copy `merchant-reset.html` and `merchant-reset.js`; `business/ui_host.py` requires these files when serving UI.
5. Confirm signed-in users are logged out once immediately following the token-format deployment. Existing tokens issued before this change omit the new password-version field.

## Security acceptance checks

- Existing account and unknown-email recovery requests return identical public 202 responses when enabled.
- Recovery link must expire after 20 minutes, fail after first use, and fail if a password changes.
- Recovering a password invalidates all previously issued bearer tokens.
- Merchant users cannot read/modify staff from another tenant, nor grant `platform_admin`.
- Owners cannot disable their own access or the last active owner.
- Non-owners cannot invite or edit staff. Stale invitation cannot reactivate a disabled user.
- Audit events preserve the actor, target, previous role/status and timestamp, without email secrets or passwords.
- Resend provider outages, rate limits, stale tokens and unavailable schema return controlled errors.
- Production merchant public self-enrollment remains disabled until approved Merchant Terms, Privacy Notice, onboarding review and anti-abuse controls are validated.

## Manual smoke sequence

1. Install dependencies from `business-requirements.txt`.
2. Run `pytest -q tests/test_business_account_security_v0623.py` from `backend`.
3. Build frontend: `cd backend/business_frontend && npm ci && npm run build`. Confirm reset files in `dist`.
4. On staging: use an active merchant account, request reset, inspect the real email, reset the password, confirm old password login fails.
5. Sign in with the new password, invite staff, accept invitation, test tenant isolation and owner controls.
6. Test disabled user login and resend-link flow.
7. Verify no Core database connection is used.

## Rollout / rollback

Apply b13 only to Business after backup. Feature flag defaults to OFF. Deploy first with reset disabled; enable only after staging evidence. If rollback is required, disable `PRUVS_BUSINESS_PASSWORD_RESET_ENABLED`, return to previous Business image, and leave the additive audit/rate tables in place. Never drop tables containing audit history merely to rollback.

## Known limitations

- The production Merchant Terms / Privacy version remains a staging placeholder in the existing enrollment flow; that is not changed here.
- A merchant's email address can belong to only one merchant because `merchant_staff.email` is globally unique in the current schema. Multi-merchant identities require a separate model redesign.
- Rate-limit persistence depends on the b13 `merchant_signup_rates` table.
- No production release, mail delivery, migration, or end-to-end tests have been executed from this work.
