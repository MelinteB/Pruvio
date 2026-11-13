# Pruvs production combined service — Core v7.1.50 / Business v0.6.6

**Release candidate**: `release/pruvs-platform-v7150-b066-combined-prod-20261113` in `MelinteB/Pruvio`.

This promotes the existing combined staging architecture to production *without copying staging credentials or data*. It is a production **release candidate**, not an instruction to change the active production service before verification.

## Target topology

- Core UI `/`, Core APIs `/api/v1/*`, Core health/readiness `/health` / `/ready`.
- Business UI `/business/`, merchant enroll `/business/merchant-enroll.html`, Business API `/business/v1/*`.
- Business health/readiness `/business/health` and `/business/ready`.
- Independent Core and Business logical PostgreSQL databases, existing production users and secrets.
- Core-to-Business loyalty calls use a fixed local loopback route `http://127.0.0.1:$PORT/business`, not a public external service.

## Blockers to resolve BEFORE changing production

1. Confirm the active Core production service, its GitHub branch, live commit, existing build/start commands, and backups in Render. GitHub `main` currently points to `b480ff1` (Core release candidate contains 27 later staging commits), so review all code changes before promoting; do not auto-merge this branch.
2. Confirm the **actual production** Core and Business database names from both Render connection strings. Do not use staging database URLs, names, or credentials. Record their exact names in `PRUVS_PRODUCTION_CORE_DB_NAME` and `PRUVS_PRODUCTION_BUSINESS_DB_NAME`.
3. Verify both production DB backups can be restored, then run read-only Business `/ready` schema checks. Business b08/b09 (and any newer) additive schema migrations must be applied separately and verified against the verified production Business DB, not from startup; never copy staging data.
4. Preserve Core's existing production `DATABASE_URL` and other environment variables. Supply `BUSINESS_DATABASE_URL` pointing to the existing **production Business** database (its current merchant records must remain intact), `BUSINESS_JWT_SECRET` with the existing production Business secret, and `PRUVS_BRIDGE_SECRET` with the existing matching production bridge secret.
5. Set `APP_ENV=production`, `PRUVS_PLATFORM_COMBINED_PRODUCTION=true`, `PRUVS_PLATFORM_COMBINED_STAGING=false`, `ENABLE_DEMO_SANDBOX=false`, and `CORS_ORIGINS=https://pruvs.io` (plus any additional explicitly approved HTTPS origins). Use distinct strong production signing secrets.
6. Keep production loyalty feature flags at their previous safe values until the smoke test is complete; turn on claims/customer codes only after testing both services.
7. Keep the standalone Business service available through the cutover and do not delete its database, service, repo, or secrets until post-cutover verification is complete.

## Render service configuration, after review

- Existing **Core production** Render Web Service, repo `MelinteB/Pruvio`, deploy branch `main`.
- Root Directory `backend`; use Python runtime. Consider pausing auto-deploy while the production change is being staged and reviewed.
- Build command (Render Bash):

```bash
pip install -r requirements.txt -r business-requirements.txt && cd frontend && npm ci && npm run build && cd .. && python scripts/check_react_build.py && cd business_frontend && npm ci && VITE_API_BASE=/business VITE_PRUVS_CUSTOMER_URL= npm run build -- --base=/business/ && cd .. && python -m pytest -q tests/test_combined_platform_routes.py tests/test_combined_database_url_v066.py tests/test_combined_production_config.py
```

- Start command (Render Bash):

```bash
exec python -m uvicorn app.platform_production:app --host 0.0.0.0 --port ${PORT:-10000}
```

This start command rejects any missing opt-in or mismatched/unknown database names. The staging `app.platform_combined` module remains staging-only.

## Production smoke checks (read-only first)

```powershell
$base = 'https://pruvs.io'
$paths = @('/health','/ready','/api/v1/release','/business/','/business/health','/business/ready','/business/merchant-enroll.html')
foreach ($path in $paths) {
    $response = Invoke-WebRequest -Uri ($base+$path) -MaximumRedirection 0 -SkipHttpErrorCheck
    Write-Host "$path : $($response.StatusCode)"
    if ($response.StatusCode -ne 200) { throw "Smoke check failed: $path" }
}
```

Also open `/business/`, confirm Business UI asset requests under `/business/assets/`, sign in with an existing production merchant, verify records, save a draft program, and test Pruvs customer loyalty visibility with an authorized test account. Validate that stamp credits require merchant approval and that no claim is duplicated. Check Core OCR, sign-in, bills, PWA and WebSocket behavior.

## Rollback

Preserve the prior successful Core production commit/branch and exact Build/Start configuration. If the combined deployment fails, restore the prior Core Start/Build command, unset `PRUVS_PLATFORM_COMBINED_PRODUCTION`, and redeploy the previous Core revision. Restore the Core loyalty API URL to the original standalone production Business endpoint if it was changed. Continue operating the original standalone Business service. No automatic database downgrade or destructive migration is part of rollback. Test both apps and both DB connections after rollback.
