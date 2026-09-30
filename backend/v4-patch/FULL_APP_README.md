# Pruvio standalone v4

Pruvio v4 is the mobile-first standalone app with receipt OCR, translation, receipt history, quantity-aware split bills, OTP registration/login, legal review gates, passkeys/WebAuthn, and developer TOTP debug authentication.

## Authentication flow

### Registration

```text
Name + email + phone
→ View Terms
→ View Privacy Notice
→ Accept both
→ Verify SMS OTP
→ Verify email OTP
→ Account active
→ Account / Security
→ Optional: add fingerprint / Face ID / passkey
```

### Returning user

```text
Preferred: fingerprint / Face ID / passkey
Fallback: email or phone OTP
Developer only: Authenticator TOTP when allow-listed
```

## Local start

From `backend`:

```powershell
.pvenv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Local passkey example environment:

```env
PUBLIC_BASE_URL=http://127.0.0.1:8000
PASSKEY_ENABLED=true
PASSKEY_RP_ID=127.0.0.1
PASSKEY_RP_NAME=Pruvio
PASSKEY_ORIGIN=http://127.0.0.1:8000
```

For Render use HTTPS and the Render hostname instead. See `V4_SECURITY_README.md`.

## Version check

```text
/health
/docs
```

Both should identify version `4.0.0` after deployment.
