# Pruvs v6.9

## Included changes

### Admin user deletion

`DELETE /users/{user_id}` now requires only the configured admin API key.
It intentionally does **not** require:

- an email OTP;
- a verified email address;
- an active user status.

The request still requires the admin header used by the existing Users API.
End-user self-service deletion from the Account UI is unchanged and continues to require email OTP confirmation.

### API documentation and OpenAI endpoints

The OpenAPI production server defaults to:

`https://pruvs.io`

It can be overridden with `PRUVS_API_BASE_URL` if needed.

New admin-only OpenAI endpoints are shown in `/docs`:

- `GET /openai/status` — configuration state and models, never the API key;
- `POST /openai/receipts/{document_id}/process` — process an existing document directly with OpenAI OCR;
- `POST /openai/translate` — directly test OpenAI receipt-item translation.

Pruvs continues to use the OpenAI Responses API internally and Azure remains the primary OCR/translation provider in the normal receipt workflow.

Required Render configuration remains:

```text
OPENAI_API_KEY=<secret>
OPENAI_RECEIPT_FALLBACK_ENABLED=true
OPENAI_TRANSLATION_FALLBACK_ENABLED=true
OPENAI_RECEIPT_MODEL=gpt-6-luna
OPENAI_TRANSLATION_MODEL=gpt-6-luna
```

Optional explicit API documentation base URL:

```text
PRUVS_API_BASE_URL=https://pruvs.io
```

The secret API key must never be committed to Git.

### iPhone Revolut button

The participant payment screen no longer attempts to open Revolut with `window.open()` after a server/WebSocket callback. iOS can block that as a popup because the original tap gesture is lost.

`Open Revolut` is now a direct HTTPS anchor to the owner's saved `revolut.me` link. The click also records the payment method as initiated through a small same-origin HTTP request. This preserves the original user gesture so iOS can hand the universal link to the Revolut app.

### Bank transfer button

`Use bank transfer` now performs a visible action. On tap it:

1. copies recipient, IBAN, bank/BIC when available, payment reference, and participant amount to the clipboard;
2. records `bank_transfer` as the initiated payment method;
3. displays a message instructing the participant to open the banking app and paste the details.

A clipboard fallback is included for browsers where `navigator.clipboard.writeText` is unavailable.

### Cache refresh

PWA/service-worker and static asset cache identifiers are bumped to `6.9.0` so iPhone/browser clients fetch the updated payment UI after deployment.

## Suggested verification

From the project root:

```powershell
& .\.pvenv\Scripts\python.exe -m compileall .\backend\app .\backend\tests

Push-Location .\backend
& ..\.pvenv\Scripts\python.exe -m unittest discover -s tests -p "test_v6_9_admin_openai_payment.py" -v
Pop-Location
```

Expected v6.9 test result: 5 tests, `OK`.

Then verify:

- `/health` reports `6.9.0`;
- `/docs` shows `https://pruvs.io` as the Pruvs API server and includes the **OpenAI** tag;
- an unverified/pending user can be deleted using only the admin API key;
- `Open Revolut` opens the saved Revolut link on iPhone;
- `Use bank transfer` copies the bank-transfer details and displays confirmation.

## OpenAI fallback import hotfix

The v6.9 release includes a compatibility fix for the current receipt normalization service.
The OpenAI direct processor now reuses `build_receipt_structure`,
`apply_basket_adjustments_proportionally`, and `finalize_receipt_items` instead of
referencing the removed `build_net_receipt_items` helper. A regression test imports
the OpenAI direct service so this mismatch is caught before deployment.
