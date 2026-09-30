# Pruvio v5 — password, verified profile changes, bilingual UI, OCR preview editing, live split bill

## New in v5

- Password can be set at registration and changed from Account.
- Password reset uses an OTP sent to the verified email address.
- Email and phone can be changed from Account; each new destination must be confirmed with its own OTP before it replaces the old value.
- Registration verification explicitly shows the normalized phone number and email destination. When `OTP_DEBUG_RETURN_CODE=true`, each debug OTP is shown next to its channel.
- User-list API includes email where available and is protected by `X-Pruvio-Admin-Key` using `PRUVIO_ADMIN_API_KEY`.
- Account deletion API is a two-step OTP flow: request OTP, then DELETE with the OTP. The service removes the user and user-owned Pruvio data.
- OpenAPI docs are curated: current Auth, Users, Registration OTP, Split Bill Sessions and Receipts are visible; old internal/legacy APIs remain callable for compatibility but are hidden from `/docs`.
- Romanian preference localizes the active standalone UI, including account, upload, receipts, history, split bill, support and legal pages.
- Receipt images are loaded into a preview/edit stage before OCR. The user can crop by edge percentages, scale, rotate and inspect the entire edited image. OCR only starts after `Send to OCR`.
- Split bill assignments saved by other participants are displayed with participant-name markers. Fully claimed lines are greyed and crossed/blocked. Session links poll for saved changes every two seconds and refresh automatically when the local participant has no unsaved edits.
- PWA cache key bumped to `pruvio-shell-v5` and navigation HTML is never cached.

## Render settings to add/verify

Keep the Render PostgreSQL `DATABASE_URL` and your existing Azure / passkey settings. Add:

```env
PRUVIO_ADMIN_API_KEY=<long random value>
OTP_DEBUG_RETURN_CODE=true   # test only; false for production
```

For the existing passkey setup on Render:

```env
PASSKEY_ENABLED=true
PASSKEY_RP_ID=pruvio.onrender.com
PASSKEY_RP_NAME=Pruvio
PASSKEY_ORIGIN=https://pruvio.onrender.com
PASSKEY_USER_HANDLE_SECRET=<secret>
```

For developer TOTP:

```env
DEV_TOTP_ENABLED=true
DEV_TOTP_ALLOWED_EMAILS=<your verified email>
DEV_TOTP_SECRET=<base32 secret>
DEV_TOTP_ISSUER=Pruvio Developer
```

## Current public API surface

- `GET /health`
- `POST /auth/password/login`
- `POST /auth/password-reset/request`
- `POST /auth/password-reset/confirm`
- registration OTP routes under `/onboarding/otp`
- current receipt routes under `/app`
- current split-session routes under `/split-bill`
- `GET /users/` (admin API key required)
- `POST /users/{user_id}/deletion/request-otp`
- `DELETE /users/{user_id}` with OTP confirmation

`GET /users/` requires the HTTP header:

```text
X-Pruvio-Admin-Key: <PRUVIO_ADMIN_API_KEY>
```

## User deletion API example

Request the OTP:

```json
POST /users/12/deletion/request-otp
{"channel":"email"}
```

Then confirm deletion:

```json
DELETE /users/12
{"channel":"email","code":"123456"}
```

When debug OTP is enabled, `debug_otp` is returned to support testing.

## Dependency fix

`requirements.txt` now includes:

```text
email-validator>=2.2
```

This fixes the Render startup error caused by Pydantic `EmailStr`.
