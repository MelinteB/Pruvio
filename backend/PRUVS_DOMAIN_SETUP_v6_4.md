# Pruvs 6.4 — pruvs.io setup and deployment

Prepared for the existing FastAPI/NiceGUI app on Render, using a domain bought at GoDaddy, Resend email OTP, Azure Document Intelligence and Azure Translator.

The app update is prepared locally. Your GoDaddy, Render, Resend and Azure account settings have not been changed from this workspace. No live email or OCR request was sent during validation.

## 1. Connect the existing Render service

Use the existing service and database that currently serve Pruvio. This is a domain and branding update, not a new database or a replacement Render service.

1. Open https://dashboard.render.com and select the existing app service.
2. Go to **Settings → Custom Domains → Add Custom Domain**.
3. Enter `pruvs.io` without `https://` or a path. Save.
4. Render also adds `www.pruvs.io` and redirects it to the root domain.
5. Keep the existing `onrender.com` address enabled so old shared links and integrations remain reachable.

In **GoDaddy → Domain Portfolio → pruvs.io → DNS**, use these records if GoDaddy is managing the domain's nameservers:

| Type | Name | Value | TTL |
| --- | --- | --- | --- |
| A | `@` | `216.24.57.1` | Default / 600 seconds |
| CNAME | `www` | `pruvio.onrender.com` | Default / 600 seconds |

Confirm the exact current `onrender.com` hostname in your Render dashboard. If it differs from `pruvio.onrender.com`, use that actual hostname in the CNAME. Do not rename the Render service just to change the brand.

Edit an existing parking A record at `@` and existing `www` CNAME instead of adding conflicting duplicates. Remove only conflicting website A/AAAA records for `@` or `www`, and turn off domain forwarding if configured. Keep NS, SOA, verification TXT records and unrelated mail records. GoDaddy uses an **A** record at the root; the earlier Cloudflare-specific root CNAME instructions do not apply.

Return to **Render → Custom Domains → Verify**. Wait for verification and the HTTPS certificate to complete, then open https://pruvs.io. Render supplies and renews the certificate.

Leave `CANONICAL_REDIRECT_ENABLED=false` or unset until this HTTPS check succeeds. The app can be deployed before the domain is ready.

## 2. Verify the sending domain in Resend

Open https://resend.com/domains and select **Add domain**:

| Field | Value |
| --- | --- |
| Name | `auth.pruvs.io` |
| Region | Ireland (`eu-west-1`) |
| Custom Return-Path | `send` |
| Click tracking | Off |
| Open tracking | Off |

The `auth` subdomain is included under your domain; no additional domain purchase is needed. Do not point `auth.pruvs.io` to Render. It is used for email authentication.

Click **Add domain → Auto Configure**, sign in to GoDaddy, review the requested DNS changes and authorize the setup. Resend uses Domain Connect to add the required sending records.

If automatic setup is unavailable, copy **exactly the records Resend shows** into GoDaddy. These commonly include a DKIM TXT/CNAME and return-path SPF/MX records. Under a `pruvs.io` DNS zone, a record shown as `send.auth.pruvs.io` normally has Name `send.auth`, and `resend._domainkey.auth.pruvs.io` has Name `resend._domainkey.auth`. Use the precise type, content and priority in your Resend dashboard; do not copy another person's DKIM key or a different region's MX target.

Enable sending and leave optional receiving disabled for OTP delivery. Return to Resend and verify the records until the sending domain shows **Verified**. Follow Resend's DMARC setup guidance for the sending domain as well. DNS changes can take time to propagate.

Your API key must have **Sending access** for `auth.pruvs.io` (or all domains). If a key was restricted to a different domain, create a sending key for this one. Enter the key directly into Render, not into source code or chat.

After verification, the sender is:

```text
Pruvs <verify@auth.pruvs.io>
```

This sender does not require a GoDaddy mailbox. It also does not create an inbox that can receive customer support messages.

## 3. Set the Render environment variables

After `https://pruvs.io` works and the Resend sending domain is verified, open **Render → existing service → Environment**. Add or update only these settings:

| Key | Value |
| --- | --- |
| `PUBLIC_BASE_URL` | `https://pruvs.io` |
| `CANONICAL_REDIRECT_ENABLED` | `true` |
| `PASSKEY_ENABLED` | `true` |
| `PASSKEY_RP_ID` | `pruvs.io` |
| `PASSKEY_RP_NAME` | `Pruvs` |
| `PASSKEY_ORIGIN` | `https://pruvs.io` |
| `EMAIL_PROVIDER` | `resend` |
| `RESEND_API_KEY` | Your private Resend sending API key |
| `EMAIL_FROM` | `Pruvs <verify@auth.pruvs.io>` |
| `OTP_DEBUG_RETURN_CODE` | `false` |
| `DEV_TOTP_ENABLED` | `false` for normal production use |
| `WHATSAPP_ENABLED` | `false` |
| `WHATSAPP_OTP_ENABLED` | `false` |
| `LOCAL_OCR_ENABLED` | `false` when using Azure OCR on Render |

Click **Save and deploy**. A redeploy is required for the new environment values to take effect.

Keep the existing values of `DATABASE_URL`, `PRUVIO_STORAGE_SECRET`, `OTP_SECRET`, `PASSKEY_USER_HANDLE_SECRET`, `PRUVIO_ADMIN_API_KEY` and the Azure keys/endpoints. Preserve existing upload storage settings. The `PRUVIO_` names are intentionally retained for compatibility; do not replace them with invented `PRUVS_` variable names.

`PUBLIC_BASE_URL` controls newly generated shared bill and QR links. The optional canonical redirect moves GET/HEAD browser page requests from the old Render hostname to the same path on `pruvs.io`, preserving bill tokens and query strings. It does not redirect API requests, uploads, health checks, webhook paths or static assets. It is off by default for safe local testing and setup.

Existing browser sessions and device trust cookies belong to the old domain. Sign in on the new domain and complete email OTP once. Old-domain passkeys cannot be used for `pruvs.io`; after signing in using email OTP/password, register a new passkey from Account on the new domain. Existing account data and bills remain in the same database.

## 4. Azure: keep the existing resources

The inspected app uploads receipt bytes from the Render backend to Azure Document Intelligence using an Azure endpoint and API key. Translation is also called by the backend using a Translator key, endpoint and region. The website domain is not used as an Azure callback or login redirect in these integrations.

Therefore, you do not need to add `pruvs.io` as an Azure custom domain, change CORS, create an Entra application or recreate the working OCR/Translator resources for this change.

Check these existing Render variables against **Azure Portal → the appropriate resource → Keys and Endpoint**:

| Render variable | Where its value comes from |
| --- | --- |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Existing Document Intelligence resource endpoint |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | A current key for that same resource |
| `AZURE_DOCUMENT_INTELLIGENCE_LOCALE` | Keep `auto` unless you deliberately configured another locale |
| `AZURE_TRANSLATOR_ENDPOINT` | Keep the working Translator endpoint, commonly `https://api.cognitive.microsofttranslator.com` |
| `AZURE_TRANSLATOR_KEY` | Existing Translator resource key |
| `AZURE_TRANSLATOR_REGION` | Actual resource region; do not assume it matches the Resend region |
| `ENABLE_RECEIPT_TRANSLATION` | `true` if translation is used |

Do not replace an Azure endpoint with `https://pruvs.io`. If OCR and translation already work, preserve their configuration. If the Azure resource uses network restrictions, it must continue allowing the existing Render backend's outbound connection; a website domain change does not change that service's identity.

## 5. Support, payments and other places

- **Support and privacy contacts:** Set `PRUVIO_SUPPORT_EMAIL` and `PRUVIO_LEGAL_CONTACT_EMAIL` to a real monitored email address you already control. Use `support@pruvs.io` only after you have separately configured an inbox or forwarding for that address. Resend's OTP sender is not a support mailbox. Keep accurate existing `PRUVIO_LEGAL_ENTITY_NAME` and `PRUVIO_LEGAL_ADDRESS` values; the brand name does not establish a company.
- **Revolut and bank transfers:** Existing Revolut.me links and bank details can remain. The app uses direct payment links and does not have a payment-provider callback domain to update. Newly generated default bill descriptions use Pruvs; saved user-entered notes are retained.
- **WhatsApp/Meta and Twilio:** Authentication is email-only. The current standalone app does not mount the legacy WhatsApp receipt or OTP webhooks, so no new WhatsApp callback should be configured as part of this rollout. These providers are not needed for email OTP.
- **GitHub:** Keep the existing repository and Render connection. A repository rename is unnecessary. The project path stays `backend/` so the current build/start commands continue to work.
- **Monitoring/bookmarks:** Point website monitors and bookmarks at `https://pruvs.io`; the health endpoint is `https://pruvs.io/health`.
- **Installed phone app:** Install/add to home screen from `https://pruvs.io` to use the new domain, name and icon. An old-domain installation is a separate browser app; its saved sign-in state does not migrate across domains.

## 6. Apply the ZIP and push from Windows

The ZIP files contain backend files at their root (`app/`, `requirements.txt`, etc.). Run these commands from the existing Git repository folder that contains `backend`. Do not delete `backend` or overwrite a real `.env` with an example file.

The update ZIP includes all changes from the previous v6.1 upload-fixed release through v6.4, so it also upgrades v6.2 and v6.3.

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\pruvs_v6_4_update.zip" -DestinationPath ".\backend" -Force
git add backend/app backend/tests backend/requirements.txt backend/.env.standalone.example backend/PRUVS_DOMAIN_SETUP_v6_4.md backend/RENDER_PRUVS_SETTINGS.env.example backend/FULL_APP_README.md backend/USER_FLOW_README.md backend/EMAIL_OTP_SETUP_v6_3.md backend/OTP_SETUP_v6_2.md
git commit -m "Rebrand app as Pruvs and support pruvs.io"
git push
```

The full alternative is `pruvs_full_app_v6_4.zip`; use it instead of the update ZIP if you need the complete backend source. Both produce the same current application when applied to the documented baseline. The ZIPs exclude actual credentials, databases, uploaded receipts and caches.

If Render has automatic deployment enabled, the push starts a deployment. Otherwise choose **Manual Deploy → Deploy latest commit**. Keep the current build/start commands, database and storage configuration.

## 7. Check the deployed app

1. Open `https://pruvs.io/health`. It should report `app: Pruvs Core`, `version: 6.4.0` and `otp_channels: [email]`.
2. Check the new Pruvs logo, blue primary buttons and navy text on desktop and mobile. Reload the page after deployment; reinstall the home-screen app from the new domain if needed.
3. Register or sign in using an email you control. Confirm the branded email arrives and the OTP popup opens only when required. Inspect Resend's email log if delivery fails.
4. Verify that a trusted browser can subsequently use its password/passkey without another routine OTP.
5. Upload a photo and a PDF. Confirm the previews and Azure OCR results work. Use a non-English/non-Romanian receipt to check translation, since those two languages intentionally keep original names.
6. Generate a new shared bill link and check that it starts with `https://pruvs.io/`. Open it using another account; the owner should see the owner warning and account-switch options.
7. Open an old shared URL on the Render hostname. With the canonical redirect enabled, its path and token should be preserved on `pruvs.io`.
8. Check phone-change confirmation via email OTP and your configured support contact. Test account deletion only on a disposable account if desired.

## What changed in v6.4

- Pruvs name throughout the current app, page titles, share messages, OTP emails and app manifest.
- Approved transparent Pruvs wordmark and a matching extracted icon, plus blue/navy styling across forms, buttons, navigation, crop controls and verification dialogs.
- Branded HTML OTP email with a plain-text fallback. The logo URL comes from the configured HTTPS `PUBLIC_BASE_URL`.
- Optional canonical browser redirects, with API/upload/health paths left on their original host.
- Updated support answers for email-only OTP and account-required shared bills.
- Existing storage identifiers, secrets, database paths, account IDs, upload behavior and payment details are retained.

## Validation performed

- 55 automated tests passed, including email delivery handling and canonical-domain redirects.
- Login, registration, account changes, account deletion and owner/shared-link UI flow checks passed.
- Full application startup and public page responses passed; logo assets, manifest icons, health output and redirects were checked. External OCR/PDF providers were stubbed for the page checks.
- The update ZIP was checked to reconstruct the current source from the v6.1 upload-fixed baseline; archives exclude actual credentials, databases and uploaded receipts.
- Browser visual rendering, physical passkeys, live DNS/TLS, Resend delivery and Azure processing still need the deployed checks above. A browser executable was unavailable in the validation environment.

## Reference documentation

- Render custom domains: https://render.com/docs/custom-domains
- Render DNS values: https://render.com/docs/configure-other-dns
- Render environment variables: https://render.com/docs/configure-environment-variables
- GoDaddy DNS records: https://www.godaddy.com/help/add-or-edit-an-a-record-42546
- Resend with GoDaddy: https://resend.com/docs/knowledge-base/godaddy
- Resend domain verification: https://resend.com/docs/add-a-domain
- Azure Document Intelligence: https://learn.microsoft.com/en-us/python/api/overview/azure/ai-documentintelligence-readme?view=azure-python
- Azure Translator: https://learn.microsoft.com/en-us/azure/ai-services/translator/text-translation/quickstart/rest-api
