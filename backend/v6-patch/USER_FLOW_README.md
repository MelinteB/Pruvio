# Pruvio v4 user flow

## New account

1. `/register`
2. Enter name, email and phone.
3. Open Terms and Privacy before acceptance becomes available.
4. Accept Terms and acknowledge Privacy.
5. Verify phone OTP and email OTP.
6. Account becomes active and the user is signed in.
7. Pruvio opens `/account` so the user can add a passkey immediately.

## Returning user

At `/` the preferred option is **Use fingerprint / Face ID / passkey**.

Fallback remains:

```text
email or phone
→ send OTP
→ verify OTP
→ dashboard
```

An allow-listed developer account can additionally use **Developer Authenticator** TOTP for debug testing.

## App

```text
Dashboard
→ Scan/upload receipt
→ OCR + validation + optional translation
→ Receipt review
→ Start split bill
→ Share participant link
→ Friends join without a Pruvio account
→ Select item quantities
```

Bottom navigation:

```text
Home · Scan · History · Account
```

There are no custom Back/Forward buttons.

## Security

Passkeys use WebAuthn. The device/platform performs fingerprint/face/device-PIN verification locally. Pruvio stores the passkey public credential and signature counter, not biometric templates.

See `V4_SECURITY_README.md` for Render settings.
