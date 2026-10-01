# Pruvs v6.4 — complete backend

This is the existing FastAPI + NiceGUI app, rebranded from Pruvio to Pruvs.

Start with **PRUVS_DOMAIN_SETUP_v6_4.md** for the exact GoDaddy, Render, Resend and Azure instructions and Windows deployment commands.

The backend entry point remains `app.main:app`. Keep the existing Render service, database, secrets and upload storage. `PRUVIO_` environment variable names and internal storage identifiers are retained for compatibility.

The current app uses unique usernames/email login, email-only OTP dialogs, trusted browsers, passkeys, document uploads, Azure OCR/translation, and owner-protected shared bills. Branding includes the Pruvs logo, blue/navy theme, app icons and HTML OTP emails. Version `/health`: `6.4.0`.

For local development, copy `.env.standalone.example` to `.env`, set your own local secrets and providers, and keep `CANONICAL_REDIRECT_ENABLED=false`. Never commit real credentials or databases.

For production, `RENDER_PRUVS_SETTINGS.env.example` contains only the public migration settings. Merge them into the existing Render configuration after the domain is verified. Add the Resend key privately in Render.
