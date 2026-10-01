> Historical setup notes. For Pruvs v6.4 and pruvs.io, use **PRUVS_DOMAIN_SETUP_v6_4.md** instead.

# Pruvio v6.3 — email OTP popups and unique usernames

## Changes

- Signup verifies email only. The phone number remains contact information; it receives no OTP and cannot be used to sign in.
- Sign in with a unique username or email, using a password or passkey. A username can be a full name.
- Username comparisons ignore capitalization, repeated spaces and compatibility Unicode forms. Usernames contain 3–80 characters, including at least one letter; letters, numbers, spaces and common name punctuation are accepted.
- Signup suggests the full name as the username and checks availability. Display names may repeat when usernames differ. Users can change their username under Account.
- Email OTP entry appears in a rounded popup only when required: signup, a new/untrusted browser, password reset, contact changes or account deletion. It includes a masked email address, resend, cancel and confirmation buttons. A delivery failure does not open an unusable popup.
- Changing a phone number sends confirmation to the account's existing verified email. The code is bound to the account and exact proposed phone number. Changing email verifies the new email address.
- Deletion requires a code sent to the account's verified email. SMS/WhatsApp deletion is rejected; an admin key alone cannot delete an account.
- A bill owner cannot join through the shared invitation link, including by reopening their existing owner participant through that route. They see: **“You are the owner of this bill and cannot join through the shared link. This link is for other users. Sign out or use another account.”**
- The warning offers **Sign out** and **Use another account**. Account switching remembers the bill link and returns there after sign-in. The owner's normal bill management page remains available from their receipt/history.
- English and Romanian interfaces are supported. The previous image/PDF upload fix, passkeys and payment/split features are included.

## Install and push — Windows PowerShell

Download `pruvio_v6_3_email_accounts.zip`. Run these from the Git repository root (the directory containing `backend`):

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\pruvio_v6_3_email_accounts.zip" -DestinationPath ".\backend" -Force
git add backend/app backend/requirements.txt backend/.env.standalone.example backend/EMAIL_OTP_SETUP_v6_3.md backend/OTP_SETUP_v6_2.md backend/FULL_APP_README.md backend/USER_FLOW_README.md backend/tests
git commit -m "Add email OTP popups, unique usernames and shared bill owner guard"
git push
```

The patch applies to the previous v6.1/v6.2 backend. It includes the prior upload fix and supporting authentication files. The full archive, `pruvio_full_app_v6_3.zip`, is available for a complete source replacement. Both archives unpack directly into `backend`; neither contains an extra enclosing folder, actual `.env`, database, uploaded documents or caches.

Keep the existing database and environment values. If a database backup is part of your deployment procedure, take it before the first v6.3 startup. Do not replace it with a fresh empty database.

## Email delivery settings

No Meta or Twilio account is needed for authentication. Keep your existing working email provider settings. For the included Resend HTTPS provider, configure these in your server environment:

```env
EMAIL_PROVIDER=resend
RESEND_API_KEY=your-resend-api-key
EMAIL_FROM=Pruvio <verify@your-verified-sending-domain>
OTP_DEBUG_RETURN_CODE=false
DEV_TOTP_ENABLED=false
TRUSTED_DEVICE_DAYS=30
WHATSAPP_OTP_ENABLED=false
```

Use a verified sending domain and credentials authorized to send from it. The app also retains its SMTP email provider option. This update prepares the code; it does not configure your provider account, DNS or Render environment.

Preserve the existing `OTP_SECRET`, `PRUVIO_STORAGE_SECRET`, database connection and passkey settings. New installations need strong random values for these secrets. Production must keep debug OTP display disabled. Authentication ignores old phone OTP enable flags and no longer mounts the WhatsApp OTP callback route.

## Existing accounts and migration

On startup, the app adds username and OTP context columns without deleting account/receipt data. It builds usernames from existing names. If names conflict, suffixes such as ` (2)` make them unique. Unusable or missing names become `User <id>`. Existing custom usernames are retained. Migration is idempotent.

Existing users can continue signing in by email and see/change their username under Account. Active accounts with an unverified email must verify it before a browser can be remembered. An account without an email requires support to add one before email authentication can work. Pending phone codes are expired during migration.

Browser trust lasts 30 days by default. A new browser/device, private window, cleared cookies, expired trust, or a password/contact change requires email OTP again. Signing out keeps the trusted-device cookie; passwords or passkeys are still required on a trusted browser.

## Verify after deployment

1. `/health` should report version `6.3.0`, `otp_channels: ["email"]` and `whatsapp_otp_enabled: false`.
2. Signup: choose an available username, complete legal acceptance, and verify one email code in the popup.
3. Sign out and sign in on the same verified browser: use username or email plus password/passkey; no OTP popup should appear.
4. Use a new/private browser: sign-in requires the email popup before establishing the session.
5. Account → Change phone number: confirm the popup lists the proposed phone and sends the code to your verified email. The phone stays unchanged until confirmation.
6. Account → Delete account: opening the popup alone does not delete anything. Correct email confirmation is required.
7. Open your own bill's shared link while signed in as its owner: see the warning and account options. Use another account to return to the same bill and join.
8. Open the bill from your receipt/history as owner: normal bill management should remain accessible. Check image and PDF uploads too.

## Validation included

```powershell
python -m pytest tests -q
python tests/check_login_ui.py
```

Install `pytest` in your development environment to run the service/API suite. Validation completed with **45 passing service/API cases** and real NiceGUI ASGI/callback checks for English/Romanian login, registration, account popups, owner access/account switching, password reset and confirmed deletion. Tests use an in-memory database and mocked email providers/OCR; they send no real messages. Live email delivery, the deployed Render service and visual browser rendering have not been verified by these tests.
