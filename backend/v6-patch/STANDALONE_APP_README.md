# Pruvio standalone app v4

Pruvio is a mobile-first standalone web/PWA receipt assistant. WhatsApp code remains optional legacy code and should stay disabled with `WHATSAPP_ENABLED=false`.

Core flow:

```text
OTP registration
→ optional passkey enrollment
→ dashboard
→ receipt upload
→ Azure Document Intelligence OCR
→ stored translations for non-RO/non-EN receipt names
→ receipt review
→ quantity-aware split bill
→ shareable participant links
```

Authentication:

- Preferred returning-user login: passkey/WebAuthn.
- Fallback: verified email or phone OTP.
- Developer-only debug: TOTP Authenticator for allow-listed email accounts.

Render keeps the existing PostgreSQL `DATABASE_URL`. Do not replace it with SQLite in production.

See `V4_SECURITY_README.md` for passkey/TOTP configuration and `FULL_APP_README.md` for start instructions.
