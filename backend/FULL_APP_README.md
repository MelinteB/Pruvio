# Pruvio standalone v6.3

Pruvio provides receipt image/PDF uploads, OCR, translation, history, quantity-aware split bills, owner tips, settlement payments, passkeys and account management.

Authentication uses unique usernames or email addresses. Signup verifies email only. A new or untrusted browser requires an email OTP in an on-demand popup; remembered browsers use a password or passkey. Phone changes and account deletion require email confirmation. Shared bill invitation links show an owner warning with sign-out/account-switch options when opened by the bill owner.

See [EMAIL_OTP_SETUP_v6_3.md](EMAIL_OTP_SETUP_v6_3.md) for installation, provider settings, migration and checks. Earlier version guides are historical.

## Local start

From `backend`, after creating/activating your Python environment and configuring `.env`:

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep the existing database when upgrading. Archives contain source code and an example environment file; they contain no actual credentials, database or user uploads. `/health` and `/docs` identify version `6.3.0`.
