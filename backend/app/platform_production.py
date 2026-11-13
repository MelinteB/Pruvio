"""Single-service Pruvs production ASGI entry point.

Hosts Core at / and Business at /business/ while keeping their databases and
security identities separate. Requires explicit production enablement and
database-name allowlists; never accepts staging databases.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.engine import make_url

if os.getenv("PRUVS_PLATFORM_COMBINED_PRODUCTION", "").strip().lower() != "true":
    raise RuntimeError("Combined production is not enabled")
if os.getenv("PRUVS_PLATFORM_COMBINED_STAGING", "").strip().lower() == "true":
    raise RuntimeError("Cannot enable staging and production combined modes together")
if os.getenv("APP_ENV", "").strip().lower() != "production":
    raise RuntimeError("Combined production requires APP_ENV=production")

core_url = os.environ.get("DATABASE_URL", "").strip()
business_url = os.environ.get("BUSINESS_DATABASE_URL", "").strip()
expected_core = os.environ.get("PRUVS_PRODUCTION_CORE_DB_NAME", "").strip()
expected_business = os.environ.get("PRUVS_PRODUCTION_BUSINESS_DB_NAME", "").strip()

if not all((core_url, business_url, expected_core, expected_business)):
    raise RuntimeError("Production requires both database URLs and explicit logical database names")
if (expected_core == expected_business or
        "stag" in expected_core.lower() or "stag" in expected_business.lower()):
    raise RuntimeError("Production database allowlists must be different and must not be staging")

core_db = make_url(core_url)
business_db = make_url(business_url)
valid_postgres_schemes = {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}
if (core_db.drivername not in valid_postgres_schemes or
        business_db.drivername not in valid_postgres_schemes):
    raise RuntimeError("Production must connect only to PostgreSQL databases")
if core_db.database != expected_core or business_db.database != expected_business:
    raise RuntimeError("Production database names do not match approved allowlists")
if core_url == business_url:
    raise RuntimeError("Core and Business must use different logical databases")

# Run the standalone Business app without its root-level SPA host.
# Mount its compiled UI explicitly beneath /business on this ASGI app.
os.environ["PRUVS_BUSINESS_SERVE_UI"] = "false"
from app.react_main import app as core_app
from business.main import app as business_app
from business.ui_host import mount_business_ui

business_dist = Path(__file__).resolve().parents[1] / "business_frontend" / "dist"
mount_business_ui(business_app, dist_dir=business_dist, enabled=True)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Starlette does not automatically run lifespans for mounted sub-apps.
    async with core_app.router.lifespan_context(core_app):
        yield

app = FastAPI(title="Pruvs Platform", lifespan=lifespan)
# Explicit /business mount takes precedence over the Core catch-all.
app.mount("/business", business_app, name="pruvs-business")
app.mount("/", core_app, name="pruvs-core")
