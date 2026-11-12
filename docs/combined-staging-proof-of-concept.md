# Combined Pruvs staging experiment

**Branch:** experiment/platform-combined-staging-20261112 (Core repository only).
**Core reference:** be9947832a609d4d49f66ae79781152709140334 (v7.1.49).
**Business reference:** 0443854355590e6a6feadf71b6f66be2d6079ccf (v0.6.5).

One Python ASGI worker mounts Core at `/` and Business at `/business/`.
Core's loyalty gateway uses fixed HTTP loopback to `127.0.0.1:$PORT/business` only when
`PRUVS_PLATFORM_COMBINED_STAGING=true`. No public external Business dependency
is needed for the combined-service loyalty bridge.

## Isolation and required environment

**Never deploy to production.**
- `PRUVS_PLATFORM_COMBINED_STAGING=true`
- `DATABASE_URL`: **existing Core staging** connection string for database `pruvs_core_staging`.
- `BUSINESS_DATABASE_URL`: **existing Business staging** connection string for `pruvs_business_staging`.
- `BUSINESS_JWT_SECRET`: from existing Business staging environment; don't expose it in logs.
- `PRUVS_BRIDGE_SECRET`: the shared staging secret used by Core and Business.
- Preserve other existing Core staging secrets and feature flags.
- Existing Business merchant API staging must remain running until this experiment is validated.
- `CANONICAL_REDIRECT_ENABLED=false` to avoid redirecting Core pages to a different service.
- Core and Business staging databases are both hard-checked at startup; startup aborts if their names are wrong.
- Frontend Vite Business build: `VITE_API_BASE=/business`, `VITE_PRUVS_CUSTOMER_URL=` (defaults to current origin), `npm run build -- --base=/business/`. This places all Business assets under /business/assets/.
- Core build remains unchanged.
- The Business sub-app owns /business/v1/* API and /business/merchant-enroll.html, and its own static assets; Core stays on /api/v1/*.
- Business standalone UI hosting is disabled inside the Business app and enabled explicitly under the /business mount.

## Build command for a separate staging Render Web Service

Render Web Service repo `MelinteB/Pruvio`, branch `experiment/platform-combined-staging-20261112`, root `backend`, Python:
```bash
pip install -r requirements.txt -r business-requirements.txt &&
cd frontend && npm ci && npm run build && cd .. &&
python scripts/check_react_build.py &&
cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. &&
python -m pytest -q tests/test_combined_platform_routes.py
```

Start:
```bash
exec python -m uvicorn app.platform_combined:app --host 0.0.0.0 --port ${PORT:-10000}
```

Warning: the combined build includes Core OCR packages and Business dependencies and may exceed the memory of Render's Free plan. No changes to production infrastructure.

## Smoke checks before retiring staging services

- `GET /` -> Core React page.
- `GET /health` -> Core health.
- `GET /business/` -> Business login page.
- `GET /business/health` -> Business health v0.6.5.
- `GET /business/merchant-enroll.html` -> enrollment page; CSS/JS load.
- `GET /business/assets/<compiled>.js` -> JS 200.
- Core customer receipt-code generation -> merchant lookup, receipt approval -> loyalty credit.
- Core WebSocket notifications and Business login/logout.
- Verify Core and Business *staging* DB identities and no prod database connections.

Do not delete the two original staging services until end-to-end checks pass.
