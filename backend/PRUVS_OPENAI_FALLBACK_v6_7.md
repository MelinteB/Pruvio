# Pruvs v6.7 — OpenAI fallback for Azure OCR and Translator

This is an **additive patch** for the current Pruvs backend. It does not replace
login, OTP, Split Bill, history, notification or currency UI files.

## New behavior

Receipt OCR:

```text
Receipt -> Azure Document Intelligence -> Pruvs
                    |
                    +-- ERROR -> OpenAI -> Pruvs
```

Translation:

```text
Receipt item names -> Azure Translator -> English when needed
                            |
                            +-- ERROR/not configured -> OpenAI -> English
```

No OpenAI request is made when the corresponding Azure operation succeeds.

## Files added

- `app/services/ocr_providers/openai_receipt_provider.py`
- `app/services/openai_receipt_direct_service.py`
- `app/services/openai_translation_service.py`
- `scripts/apply_v6_7_openai_fallback.py`
- `scripts/check_openai_api.py`
- `OPENAI_FALLBACK.env.example`
- `PRUVS_OPENAI_FALLBACK_v6_7.md`

The patch script modifies only:

- `app/services/azure_receipt_direct_service.py`
- `app/services/receipt_translation_service.py`
- `requirements.txt`

Before editing those files it creates `.bak_v6_7_openai` backups.

## Apply from Windows PowerShell

Run these commands from the Git repository root (the folder that contains
`backend`). Commit your current work before applying the patch.

```powershell
git status

Expand-Archive `
  -Path "$env:USERPROFILE\Downloads\pruvs_v6_7_openai_fallback.zip" `
  -DestinationPath ".\backend" `
  -Force

python .\backend\scripts\apply_v6_7_openai_fallback.py

.\backend\.pvenv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\backend\.pvenv\Scripts\python.exe -m compileall .\backend\app .\backend\scripts
```

If your virtual environment has a different path, use its Python executable.

## Local environment

For local development only, put the real key in `backend/.env` (which must stay
out of Git) or set it in your shell. Never put the secret in source code,
GitHub, screenshots or the example env file.

Example local values:

```dotenv
OPENAI_API_KEY=sk-...your-real-key...
OPENAI_RECEIPT_FALLBACK_ENABLED=true
OPENAI_TRANSLATION_FALLBACK_ENABLED=true
OPENAI_RECEIPT_MODEL=gpt-6-luna
OPENAI_TRANSLATION_MODEL=gpt-6-luna
OPENAI_RECEIPT_IMAGE_DETAIL=high
OPENAI_RECEIPT_PDF_DETAIL=high
OPENAI_TIMEOUT_SECONDS=60
OPENAI_RECEIPT_MAX_OUTPUT_TOKENS=5000
```

## Render environment

In Render open the Pruvs Web Service -> **Environment** and add the same variables:

```text
OPENAI_API_KEY=<your OpenAI project/service-account secret>
OPENAI_RECEIPT_FALLBACK_ENABLED=true
OPENAI_TRANSLATION_FALLBACK_ENABLED=true
OPENAI_RECEIPT_MODEL=gpt-6-luna
OPENAI_TRANSLATION_MODEL=gpt-6-luna
OPENAI_RECEIPT_IMAGE_DETAIL=high
OPENAI_RECEIPT_PDF_DETAIL=high
OPENAI_TIMEOUT_SECONDS=60
OPENAI_RECEIPT_MAX_OUTPUT_TOKENS=5000
```

Keep all existing Azure variables. **Do not remove Azure**; it remains primary.
Save/deploy after adding the variables.

## Optional local API-key test

After `OPENAI_API_KEY` is available locally:

```powershell
.\backend\.pvenv\Scripts\python.exe .\backend\scripts\check_openai_api.py
```

Expected output includes:

```text
OpenAI API connection: OK
Response: PRUVS_OPENAI_OK
```

## Production-safe functional test

Do not deliberately break the production Azure key. Use a local/staging Render
service for failure testing.

1. First upload a normal receipt with valid Azure credentials. It should still
   return `provider=azure_receipt`.
2. In staging/local only, temporarily use an invalid Azure Document Intelligence
   key while keeping `OPENAI_API_KEY` valid.
3. Upload a receipt. It should complete with `provider=openai_receipt` and
   `fallback_used=true`.
4. Restore the valid Azure credential.
5. For translation fallback, temporarily use an invalid Azure Translator key in
   staging/local and upload a non-RO/non-EN receipt.
6. Restore the valid Azure Translator credential.

The Azure failure remains recorded in the existing ExternalOCRRequest audit
trail and the OpenAI fallback creates a separate completed OCR request.

## Suggested Git commit

From the repository root:

```powershell
git add backend/app backend/scripts backend/requirements.txt `
  backend/OPENAI_FALLBACK.env.example `
  backend/PRUVS_OPENAI_FALLBACK_v6_7.md

git commit -m "Add OpenAI fallback for Azure OCR and translation"
git push
```

If Render Auto-Deploy is enabled, the push deploys the new version. Otherwise
use Render -> Manual Deploy -> Deploy latest commit.

## Rollback

The patcher keeps backups ending in `.bak_v6_7_openai`. Git is the preferred
rollback method if the files were committed before patching.
