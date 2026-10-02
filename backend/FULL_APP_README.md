# Pruvs v6.5 — complete backend

This is the FastAPI + NiceGUI Pruvs backend. The backend entry point remains `app.main:app`. Keep the existing Render service, database, secrets and upload storage. `PRUVIO_` environment variable names and internal storage identifiers remain for compatibility.

Version `/health`: `6.5.0`.

The current app includes email/password/passkey authentication, email OTP dialogs, trusted browsers, receipt image/PDF upload, Azure OCR/translation, quantity-aware split bills, per-person percentage tips, open/settled split history, owner-only reopening, direct owner payment details, automatically derived `first.surname` usernames, and Pruvs browser/PWA/share-preview branding.

For the v6.5 changes and deployment commands, see **PRUVS_UPDATE_v6_5.md**. For the existing `pruvs.io`, Render, Resend and Azure domain/provider setup, see **PRUVS_DOMAIN_SETUP_v6_4.md**; those environment settings remain applicable.

For local development, copy `.env.standalone.example` to `.env`, set your own local secrets and providers, and keep `CANONICAL_REDIRECT_ENABLED=false`. Never commit real credentials or databases.
