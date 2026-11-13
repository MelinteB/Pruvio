"""Staging experiment: one ASGI worker hosts Pruvs Core and Pruvs Business.

The applications preserve separate FastAPI objects, auth, API prefixes, databases,
and release cycles. No production service should use this entry point.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
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

# The Business ASGI app is mounted under /business. Disable its standalone
# root-level UI mounting before importing it and mount dist under the sub-app.
os.environ["PRUVS_BUSINESS_SERVE_UI"] = "false"
from app.react_main import app as core_app
from business.main import app as business_app
from business.ui_host import mount_business_ui

business_dist = Path(__file__).resolve().parents[1] / "business_frontend" / "dist"
mount_business_ui(business_app, dist_dir=business_dist, enabled=True)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Mounted FastAPI sub-apps do not automatically run their own lifespans.
    async with core_app.router.lifespan_context(core_app):
        yield

app = FastAPI(title="Pruvs Platform (Staging Experiment)", lifespan=lifespan)
# Order matters: /business must come before the Core root catch-all.
app.mount("/business", business_app, name="pruvs-business")
app.mount("/", core_app, name="pruvs-core")
