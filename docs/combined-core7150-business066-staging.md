# Combined staging release — Core v7.1.50 + Business v0.6.6

Release branch: `release/pruvs-platform-v7150-b066-combined-stage-20261112`.
Core base: `be9947832a609d4d49f66ae79781152709140334`.
Business base: `0443854355590e6a6feadf71b6f66be2d6079ccf`.
Neither application production service or database is to be changed.

## Deployment prerequisite — fix Business stage database BEFORE switching

The independent Business staging service is currently suspended in Render. The previously observed
`/v1/promotions` error `UndefinedColumn: loyalty_promotions.media_url` also shows that its
database is missing the additive b08/b09 migrations. Verify the staging database backup
and ensure revisions `b08a0149media` and `b09c0149codes` have completed, using
`Pruvs-Business/backend/scripts/check_stage_schema_v066.py`. The schema check is read-only.
Perform Alembic `upgrade head` only on verified `pruvs_business_staging` with
username `pruvs_business_stage` after a tested, restorable database backup.
No migration is automatically executed by the combined platform service.

## Render STAGING service configuration

Use existing Pruvs-staging Web Service, ID `srv-dbkrcaui0phs73b3h7p0`.
- Repository `MelinteB/Pruvio`
- Branch `release/pruvs-platform-v7150-b066-combined-stage-20261112`
- Root Directory `backend`
- Runtime Python, Auto Deploy OFF
- `DATABASE_URL`: **Core staging** DB named `pruvs_core_staging`, not production
- `BUSINESS_DATABASE_URL`: **Business staging** DB named `pruvs_business_staging`, not production
- `BUSINESS_JWT_SECRET`: same as current Business staging (do not show in logs)
- `PRUVS_BRIDGE_SECRET`: matching staging bridge secret from both apps
- `PRUVS_PLATFORM_COMBINED_STAGING=true`
- `CANONICAL_REDIRECT_ENABLED=false`
- Keep existing Core staging env including OCR and frontend flags.
- Set `VITE_GOOGLE_MAPS_EMBED_KEY` at build time only if Maps Embed API is configured; otherwise show the built-in city search and a link to Google Maps. This key is public client-side and must be domain/API restricted.

### Build Command (Render Bash)
```bash
pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_combined_platform_routes.py tests/test_stage_schema_v066.py
```
### Start Command (Render Bash)
```bash
exec python -m uvicorn app.platform_combined:app --host 0.0.0.0 --port ${PORT:-10000}
```

Core root `/`, APIs `/api/v1/*`, release `/api/v1/release`.
Business root `/business/`, APIs `/business/v1/*`, liveness `/business/health`, readiness `/business/ready`.
After Render reports Live, run
`scripts/Verify-Pruvs-Combined-Staging-v7150-b066.ps1`
from PowerShell to check HTTP status and API readiness, then test user login and merchant actions.
**No automatic receipt stamps**: receipt claims require explicit owner consent and merchant verification.

## Rollback

Do not delete either original repository or staging service. Keep backup and prior Render
Build/Start command. If the combined deployment fails, restore the original successful
Core staging branch `staging/pruvs-core-ux-20261110`, Build/Start command,
and disable `PRUVS_PLATFORM_COMBINED_STAGING`. Resume standalone
`pruvs-business-api-staging` for the separated API until integration is verified.
Never run Alembic downgrade automatically; the b08/b09 migrations are additive and
intentionally prohibit destructive downgrade. Confirm Core and Business staging
database connections by name/role before rollback or redeploy.
