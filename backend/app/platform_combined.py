"""Staging experiment: one ASGI worker hosts Pruvs Core and Pruvs Business.

The applications preserve separate FastAPI objects, auth, API prefixes, databases,
and release cycles. No production service should use this entry point.
"""
from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

if os.getenv("PRUVS_PLATFORM_COMBINED_STAGING", "").strip().lower() != "true":
    raise RuntimeError("Combined platform is disabled outside the isolated staging experiment")

core_url = os.environ.get("DATABASE_URL", "")
business_url = os.environ.get("BUSINESS_DATABASE_URL", "")
if not core_url or not business_url:
    raise RuntimeError("Both Core DATABASE_URL and BUSINESS_DATABASE_URL are required")

core_db = make_url(core_url)
business_db = make_url(business_url)
if core_db.database != "pruvs_core_staging":
    raise RuntimeError("Refusing to start combined staging on a non-staging Core database")
if business_db.database != "pruvs_business_staging":
    raise RuntimeError("Refusing to start combined staging on a non-staging Business database")
if core_url == business_url:
    raise RuntimeError("Core and Business may not share the same logical database")

# After the isolated staging reset both logical databases exist on the same
# explicitly verified pruvs-db PostgreSQL instance. Stale staging environment
# URLs must not silently route Core or Business to the recovery-test instance.
# Derive both logical names from an existing correct Render secret; never log it.
EXPECTED_STAGE_HOST = "dpg-dacoe2rm8hqs73binaq0-a"
if os.getenv("PRUVS_PLATFORM_COMBINED_PRODUCTION", "").lower() == "true":
    raise RuntimeError("Combined staging cannot run with the production flag enabled")
primary = next((url for url in (core_db, business_db)
                if EXPECTED_STAGE_HOST in (url.host or "")), None)
if primary is None:
    raise RuntimeError("Refusing staging: both database URLs miss the verified pruvs-db host")
if primary.drivername not in ("postgres", "postgresql", "postgresql+psycopg"):
    raise RuntimeError("Staging requires PostgreSQL")
os.environ["DATABASE_URL"] = primary.set(database="pruvs_core_staging").render_as_string(hide_password=False)
os.environ["BUSINESS_DATABASE_URL"] = primary.set(database="pruvs_business_staging").render_as_string(hide_password=False)
logging.getLogger("pruvs.staging.platform").warning(
    "Combined staging: using verified pruvs-db instance for both staging logical databases"
)

# The Business ASGI app is mounted under /business. Disable its standalone
# root-level UI mounting before importing it and mount dist under the sub-app.
os.environ["PRUVS_BUSINESS_SERVE_UI"] = "false"
from app.react_main import app as core_app
from app.db.database import engine as core_engine
from business.main import app as business_app
from business.db import engine as business_engine
from business.models_v0618 import MerchantStorePlace
from business.ui_host import mount_business_ui

business_dist = Path(__file__).resolve().parents[1] / "business_frontend" / "dist"
mount_business_ui(business_app, dist_dir=business_dist, enabled=True)

def _verify_schema(connection, expected_database, required_tables):
    if connection.scalar(text("SELECT current_database()")) != expected_database:
        raise RuntimeError("Staging database selection unexpectedly changed")
    if connection.scalar(text("SELECT to_regnamespace('public')")) is None:
        raise RuntimeError("Missing public schema in " + expected_database + "; verify staging migration")
    existing = set(inspect(connection).get_table_names(schema="public"))
    missing = required_tables - existing
    if missing:
        raise RuntimeError("Staging schema mismatch in " + expected_database
                           + "; required tables missing: " + ", ".join(sorted(missing)))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Mounted FastAPI sub-apps do not automatically run their own lifespans.
    # Validate the already-rebuilt Core and Business schemas before startup.
    # Nothing below ever wipes a table or touches the production DB names.
    with core_engine.connect() as conn:
        _verify_schema(conn, "pruvs_core_staging", {"users", "pruvs_social_accounts"})
    with business_engine().begin() as conn:
        _verify_schema(conn, "pruvs_business_staging",
                       {"merchants", "merchant_staff",
                        "merchant_staff_actions_v1", "merchant_signup_rates"})
        # The 2026-11-23 reset already includes the Places table; checkfirst
        # therefore performs no DDL on the freshly migrated staging schema.
        MerchantStorePlace.__table__.create(bind=conn, checkfirst=True)
    async with core_app.router.lifespan_context(core_app):
        yield

app = FastAPI(title="Pruvs Platform (Staging Experiment)", lifespan=lifespan)
# Order matters: /business must come before the Core root catch-all.
app.mount("/business", business_app, name="pruvs-business")
app.mount("/", core_app, name="pruvs-core")
