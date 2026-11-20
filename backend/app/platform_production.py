"""Production ASGI entrypoint for the Pruvs Core and Business platform.

Core and Business keep separate application objects, authentication domains and
PostgreSQL databases. Database migrations are deliberately not executed during
startup; Render's reviewed pre-deploy step owns schema changes.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.engine import make_url


if os.getenv("APP_ENV", "").strip().lower() != "production":
    raise RuntimeError("The production platform entrypoint requires APP_ENV=production")

core_url = os.environ.get("DATABASE_URL", "").strip()
business_url = os.environ.get("BUSINESS_DATABASE_URL", "").strip()
if not core_url or not business_url:
    raise RuntimeError("Both Core DATABASE_URL and BUSINESS_DATABASE_URL are required")
if make_url(core_url).render_as_string(hide_password=True) == make_url(business_url).render_as_string(hide_password=True):
    raise RuntimeError("Core and Business must use separate logical databases")

# Business owns /business and its own assets. Disable its root UI mount before
# import so it cannot shadow Core's routes.
os.environ["PRUVS_BUSINESS_SERVE_UI"] = "false"
os.environ["PRUVS_PLATFORM_COMBINED_PRODUCTION"] = "true"
from app.react_main import app as core_app
from business.main import app as business_app
from business.ui_host import mount_business_ui

business_dist = Path(__file__).resolve().parents[1] / "business_frontend" / "dist"
mount_business_ui(business_app, dist_dir=business_dist, enabled=True)

app = FastAPI(title="Pruvs Platform")
app.mount("/business", business_app, name="pruvs-business")
app.mount("/", core_app, name="pruvs-core")
