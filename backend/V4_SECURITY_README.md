# Pruvio v4 security upgrade

This package adds two authentication paths on top of the existing email/SMS OTP flow:

1. **Passkeys / WebAuthn** for fingerprint, Face ID, Windows Hello, Android biometrics, device PIN or a security key.
2. **Developer Authenticator (TOTP)** for debug access to explicitly allow-listed developer accounts.

## What changed

- Pruvio version is now `4.0.0`.
- New database table: `passkey_credentials`.
- New service: `app/services/passkey_service.py`.
- New service: `app/services/totp_debug_service.py`.
- Login page now offers **Use fingerprint / Face ID / passkey** before OTP.
- Account > Security lets a signed-in user add, list and remove passkeys.
- New registrations go to Account/Security after email + phone verification so a passkey can be added immediately.
- Developer TOTP is only available when both `DEV_TOTP_ENABLED=true` and the account email is in `DEV_TOTP_ALLOWED_EMAILS`.
- Terms/Privacy drafts now explain passkey use and that biometric templates remain on the user's device/platform.
- PWA cache version bumped to `pruvio-shell-v4`; authenticated HTML is not cached.

## Dependency

Add to `backend/requirements.txt`:

```text
webauthn>=2.2.0,<3.0
```

The supplied full package already contains an updated `requirements.txt`.

## Render environment

Keep your existing PostgreSQL `DATABASE_URL`, Azure, SMTP/SMS and app variables. Add:

```env
WHATSAPP_ENABLED=false

PASSKEY_ENABLED=true
PASSKEY_RP_ID=pruvio.onrender.com
PASSKEY_RP_NAME=Pruvio
PASSKEY_ORIGIN=https://pruvio.onrender.com
PASSKEY_USER_HANDLE_SECRET=<LONG RANDOM SECRET>

DEV_TOTP_ENABLED=true
DEV_TOTP_ALLOWED_EMAILS=<YOUR VERIFIED PRUVIO EMAIL>
DEV_TOTP_SECRET=<BASE32 SECRET GENERATED ONCE>
DEV_TOTP_ISSUER=Pruvio Developer

# Once TOTP is working, do not expose OTPs in the UI:
OTP_DEBUG_RETURN_CODE=false
```

`PASSKEY_RP_ID` is the hostname only. Do not include `https://`.

### Generate secrets locally

PowerShell examples:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use that for `PASSKEY_USER_HANDLE_SECRET`.

Generate a Base32 TOTP master secret:

```powershell
python -c "import secrets,base64; print(base64.b32encode(secrets.token_bytes(20)).decode().rstrip('='))"
```

Use that for `DEV_TOTP_SECRET` and keep it only in Render/local environment variables.

## Database

`Base.metadata.create_all()` creates `passkey_credentials` automatically when the app starts.

A manual PostgreSQL fallback is included at:

```text
scripts/passkey_postgres_migration.sql
```

Normally you should **not** need to run it manually.

## First Render test

1. Deploy v4.
2. Open `/health` and confirm:
   - `version: 4.0.0`
   - `passkeys_enabled: true`
   - `developer_totp_enabled: true` if you enabled it.
3. Sign in once with email/SMS OTP.
4. Open **Account > Security**.
5. Under Developer Authenticator, scan the QR with Microsoft Authenticator / Google Authenticator / 1Password / Authy and verify one code.
6. Add a passkey from the same Security page.
7. Sign out.
8. On the login page choose **Use fingerprint / Face ID / passkey**.

## Important domain note

Passkeys are cryptographically bound to the WebAuthn RP ID/domain. A passkey created for `pruvio.onrender.com` is a test credential for that domain. If you later move Pruvio to a custom production domain, users should register new passkeys on the final domain.

## Security note

Pruvio does **not** receive the user's actual fingerprint or face template. The operating system/platform authenticator performs the biometric check locally and Pruvio verifies the resulting WebAuthn signature.

The Developer Authenticator flow is intentionally a debug mechanism. Keep the allow-list limited to your own verified developer account and disable it before a broader production release if you no longer need it.
