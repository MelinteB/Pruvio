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

# Both logical staging DBs live on the same verified Render PostgreSQL
# instance but use DIFFERENT dedicated roles. Never reuse Core credentials
# to access Business; PostgreSQL correctly denies cross-database CONNECT.
EXPECTED_STAGE_HOST = "dpg-dacoe2rm8hqs73binaq0-a"
if os.getenv("PRUVS_PLATFORM_COMBINED_PRODUCTION", "").lower() == "true":
    raise RuntimeError("Combined staging cannot run with production mode enabled")
for name, url in (("Core", core_db), ("Business", business_db)):
    if EXPECTED_STAGE_HOST not in (url.host or ""):
        raise RuntimeError(name + " staging URL points to the wrong database server")
    if url.drivername not in ("postgres", "postgresql", "postgresql+psycopg"):
        raise RuntimeError(name + " staging requires PostgreSQL")
if core_db.username == business_db.username:
    raise RuntimeError("Combined staging requires separate Core and Business database roles")
logging.getLogger("pruvs.staging.platform").warning(
    "Combined staging: verified isolated Core and Business DB connections configured"
)

# The Business ASGI app is mounted under /business. Disable its standalone
# root-level UI mounting before importing it and mount dist under the sub-app.
os.environ["PRUVS_BUSINESS_SERVE_UI"] = "false"
from app.react_main import app as core_app
from app.db.database import engine as core_engine, Base as CoreBase
from business.main import app as business_app
from business.db import engine as business_engine, Base as BusinessBase
from business.models_v0618 import MerchantStorePlace
from business.ui_host import mount_business_ui

business_dist = Path(__file__).resolve().parents[1] / "business_frontend" / "dist"
mount_business_ui(business_app, dist_dir=business_dist, enabled=True)

def _verify_schema(connection, expected_database, mapped_tables, required_tables):
    if connection.scalar(text("SELECT current_database()")) != expected_database:
        raise RuntimeError("Staging database selection unexpectedly changed")
    if connection.scalar(text("SELECT to_regnamespace('public')")) is None:
        raise RuntimeError("Missing public schema in " + expected_database + "; verify staging migration")
    inspector = inspect(connection)
    existing = set(inspector.get_table_names(schema="public"))
    missing = (set(mapped_tables) | required_tables) - existing
    if missing:
        raise RuntimeError("Staging schema mismatch in " + expected_database
                           + "; required tables missing: " + ", ".join(sorted(missing)))
    for name in mapped_tables:
        model = mapped_tables[name]
        expected_columns = set(model.columns.keys())
        actual_columns = {c["name"] for c in inspector.get_columns(name, schema="public")}
        absent_columns = expected_columns - actual_columns
        if absent_columns:
            raise RuntimeError("Staging schema mismatch: missing " + name + " columns "
                               + ", ".join(sorted(absent_columns)))
    if expected_database == "pruvs_core_staging":
        unique_username = any(
            index["name"] == "ix_users_username_key" and bool(index["unique"])
            for index in inspector.get_indexes("users", schema="public")
        )
        if not unique_username:
            raise RuntimeError("Core staging missing unique username index; migrate before boot")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Mounted FastAPI sub-apps do not automatically run their own lifespans.
    # Validate the already-rebuilt Core and Business schemas before startup.
    # Nothing below ever wipes a table or touches the production DB names.
    with core_engine.connect() as conn:
        _verify_schema(conn, "pruvs_core_staging", CoreBase.metadata.tables,
                       {"users", "pruvs_social_accounts"})
    with business_engine().begin() as conn:
        _verify_schema(conn, "pruvs_business_staging", BusinessBase.metadata.tables,
                       {"merchants", "merchant_staff",
                        "merchant_staff_actions_v1", "merchant_signup_rates"})
        # The migration already created all tables. Runtime must never own or
        # create tables, including Google Places links.
    async with core_app.router.lifespan_context(core_app):
        yield

app = FastAPI(title="Pruvs Platform (Staging Experiment)", lifespan=lifespan)
# Order matters: /business must come before the Core root catch-all.
app.mount("/business", business_app, name="pruvs-business")
app.mount("/", core_app, name="pruvs-core")
