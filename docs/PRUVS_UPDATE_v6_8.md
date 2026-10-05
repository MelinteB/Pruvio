# Pruvs v6.8

## Purpose

Pruvs v6.8 fixes the receipt upload error:

`Message too long — The message is too large for WebSocket transmission`

The v6.7 Azure -> OpenAI fallback remains unchanged.

## What changed

- Cropped receipt images are no longer converted to a large Base64/Data URL and returned through NiceGUI WebSockets.
- Receipt image selection and preview stay in the browser using an object URL.
- Cropping is performed in the browser with Cropper.js.
- The cropped image is resized to a maximum 2400 x 2400 canvas and encoded as JPEG at quality 0.86.
- The final image is uploaded with `fetch()` using `multipart/form-data` to `/app/receipts/browser-upload`.
- PDFs are previewed through a browser object URL and uploaded directly over HTTP multipart.
- The HTTP upload endpoint is protected by a signed, short-lived token tied to the logged-in user.
- Maximum accepted upload remains 10 MB.
- PWA/static cache version is bumped to `6.8.0`.
- `/health` and the FastAPI application version now report `6.8.0`.

## Security / environment

No new Render environment variable is required.

The browser-upload token uses, in this order:

1. `PRUVS_UPLOAD_TOKEN_SECRET` if configured; otherwise
2. existing `PRUVIO_STORAGE_SECRET`; otherwise
3. the existing local-development fallback used by Pruvs.

For production, `PRUVIO_STORAGE_SECRET` should already be configured with a strong secret. Do not commit real secrets to Git.

## Install

From the Pruvs project root, extract this release over the project:

```powershell
Expand-Archive `
  -Path "$env:USERPROFILE\Downloads\pruvs_v6_8_release.zip" `
  -DestinationPath "." `
  -Force
```

Then validate:

```powershell
& .\.pvenv\Scripts\python.exe -m compileall .\backend\app .\backend\tests
& .\.pvenv\Scripts\python.exe -m unittest .\backend\tests\test_browser_upload_token_service.py -v
```

Review changes:

```powershell
git status
git diff -- backend/app backend/tests docs/PRUVS_UPDATE_v6_8.md
```

Commit only after the validation succeeds.

## Expected receipt flow

Browser file -> local preview/crop -> local JPEG resize/compression -> HTTP multipart upload -> backend -> Azure Receipt OCR -> OpenAI fallback only when Azure fails -> receipt screen.

Large image data is not sent through NiceGUI WebSocket messages in this flow.
