# Pruvs staging — Core 7.1.62 and Business 0.6.18
Prepared November 19, 2026. The release is staging-only; production main is unchanged.

## Implemented
- Loyalty: redeemed voucher closes its membership only when no stamps, pending receipts or unredeemed rewards remain. The old voucher and reconciliation ledger remain immutable. Join starts a new cycle with zero stamps.
- Historical stale memberships: one-time manual reconciliation script (dry-run default), requires staging backup, before customers rejoin; NEVER automatically delete other entitlements.
- Campaigns: Direct republish of paused or expired offers, with matching Business and Core visibility rules. Core Home and Rewards show live promotions in carousels. Rewards displays one card per campaign and reserves the regular offer list for other loyalty programs.
- Core: verified receipt stamp request moved into My wallet; Saved receipts remains browse-only, reward QR available after approvals and merchant checkout verification.
- Places: authenticated merchant Google Places New text search, optional store-to-place ID link, Google review/rating lookup on demand with attribution and Google/Apple/Waze directions.
- Language: EN/RO labels and helper text in campaign management, program setup, and location management. Campaign content keeps its authoring language.
- Design: improved responsive photographic creative, editorial gradient/text and matched Core/Business card typography.

## Preconditions
1. Confirm the exact Render staging service branch and deployed commit. It previously pointed to a design branch while the release work was merged into a different branch. Do not assume a PR merge automatically changes what Render deploys.
2. Identify and verify the staging database; do not confuse it with the production or recovery-test database. Take a tested, recoverable backup before any SQL or cleanup.
3. Server-only PRUVS_GOOGLE_PLACES_API_KEY must be configured with Places API New, billing, quotas and access restrictions. Never put this in VITE_ variables.
4. Optional VITE_GOOGLE_MAPS_EMBED_KEY is a separate browser key, referrer-restricted to staging and Maps Embed API, needed only to render an in-app map. External Google/Apple/Waze directions work without it.
5. To link Google Places, apply backend/business_migrations/versions/b12a0618_google_place_links.sql to the verified staging Business database ONLY, then verify merchant_store_google_place_v0618 exists. This table stores Place IDs, not Google names/reviews/ratings.
6. If old users remain joined after a redeemed voucher, dry-run backend/scripts/reconcile_legacy_completed_loyalty_v0618.py before rollout. Apply only once on staging after verified backup with --apply --backup-id VERIFIED_ID. Historical reward and receipt ledgers are retained. Do not run after customers restart cycles.
7. Keep existing R2 campaign media and provider AI settings; Google billing and AI generation may incur charges.

## Windows PowerShell verification and deployment review
```powershell
Set-Location 'C:\Users\bogdan.melinte\Personal\Project\Pruvs'
git fetch origin
git switch fix/rejoin-after-redeemed-v7162-b0618-20261119
git pull --ff-only origin fix/rejoin-after-redeemed-v7162-b0618-20261119
git status --short
Set-Location backend
if (-not (Test-Path .pvenv\Scripts\python.exe)) { py -3 -m venv .pvenv }
$py = (Resolve-Path .pvenv\Scripts\python.exe).Path
& $py -m pip install -r requirements.txt -r business-requirements.txt
& $py -m pytest -q tests/test_loyalty_rejoin_after_redemption_v0618.py tests/test_campaign_republish_sync_v0618.py tests/test_google_places_v0618.py tests/test_campaign_library_v0615.py tests/test_wallet_legacy_v068.py tests/test_combined_platform_routes.py
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
Push-Location frontend
npm ci
npm test -- --run
if ($LASTEXITCODE -ne 0) { throw 'Core React tests failed' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Core build failed' }
Pop-Location
& $py scripts/check_react_build.py
if ($LASTEXITCODE -ne 0) { throw 'Core build manifest mismatch' }
Push-Location business_frontend
npm ci
$env:VITE_API_BASE = '/business'
$env:VITE_PRUVS_CUSTOMER_URL = ''
npm run build -- --base=/business/
if ($LASTEXITCODE -ne 0) { throw 'Business build failed' }
Pop-Location
Set-Location ..
git diff --check
git status --short
```

## Test the campaign cycle on staging

1. In Business, select RO and open **Locations** and **Campaign Library**. Check the form labels, descriptions, search, and status text in Romanian. Merchant-authored campaign copy uses the language in which it was saved.
2. Add a test location. With Google Places enabled, search for a business, choose the result, confirm the store information, and save. Verify the linked result appears after refreshing. With Places unavailable, enter the store name, address, latitude, and longitude manually and save.
3. Publish a loyalty program for the test location. Create a test campaign for that program and preview it. It should appear in Business as a draft until you select **Publish**.
4. In Core, sign in as a separate test customer. Check Home and Rewards. The published campaign should appear once per view. To test carousel navigation, publish a second campaign for a different test program, move between cards with the controls, and check that every campaign remains reachable at a narrow viewport.
5. Join the first campaign and check it in **My wallet**. Add the program's required number of eligible test receipts and generate each receipt's QR. In Business, open each QR, review the evidence, and approve the complete package. Check the voucher in Core, complete the merchant redemption, and verify the customer can start a fresh cycle with zero stamps.
6. Unpublish the test campaign in Business. Return to Core and check that the campaign disappears after refresh. The underlying published program can still be available as a loyalty offer. In Business, republish the campaign and verify its new end date. Unpublish and archive the test campaign when finished. This preserves memberships and receipt and voucher history.

## Acceptance matrix
- Campaign: draft invisible, publish visible, unpublish absent after Core tab focus, republish visible with new date. Paused/expired/private programs/locations and cross-merchant access blocked.
- Voucher: join for 3 verified purchases, approve each, available reward, reserve QR, merchant verifies completed sale reference, redeem, customer rejoins with zero stamps. Double redemption blocked, historical ledger remains.
- Wallet: receipt claims never auto-award stamps; QR never shown before merchant approval, pending claims or active balances prevent clearing cycle.
- Places: search, select, link, view live reviews with author attribution, open directions, disconnect; expect controlled 503 when key/migration absent.
- EN/RO: switching changes primary labels and AI predefined brief/output language without erasing merchant-edited instructions.
- Devices: Android Chrome, iOS Safari, tablet, desktop at widths 320, 360, 390, 430, 768, 1024, 1440px; test keyboard, focus, reduced motion and video controls.
- Resilience: HTTP 401/403/409/429/502/503, expired R2 media, Google quota, stale Core tab, offline return and role/account isolation.

## Production go/no-go and rollback
Automated CI is necessary but not sufficient: actual merchant and customer acceptance, device audit, quotas, privacy and backup recovery must pass. On failure, redeploy the previous staging commit, keep additive b12 table and all audit records, and run controlled smoke tests. Production is separately approved.
