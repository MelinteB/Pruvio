"""Production release metadata and small resource-management helpers.

This module intentionally uses only Python standard-library dependencies so it
can be exercised without starting the Pruvs API, making network calls, or
opening the database.
"""
from __future__ import annotations
import os
from pathlib import Path

RELEASE = "7.1.18"

def bounded_seconds(name: str, default: float, minimum: float, maximum: float) -> float:
    """Use safe runtime polling limits even with an invalid environment value."""
    try:
        value = float(os.getenv(name, str(default)))
        if minimum <= value <= maximum:
            return value
    except (TypeError, ValueError, OverflowError):
        pass
    return default


def require_postgres_if_enabled(url: str | None = None) -> None:
    """Opt-in production guard; never silently migrates or rewrites a DB URL."""
    if os.getenv("PRUVS_REQUIRE_POSTGRES", "false").strip().lower() not in ("1", "true", "yes"):
        return
    raw = url if url is not None else os.getenv("DATABASE_URL", "")
    if not raw.startswith(("postgresql://", "postgres://", "postgresql+psycopg2://", "postgresql+psycopg://")):
        raise RuntimeError("PRUVS_REQUIRE_POSTGRES is enabled but DATABASE_URL does not reference PostgreSQL.")


def frontend_is_ready(frontend: Path) -> bool:
    """Check that the served build has HTML and at least one referenced bundle."""
    html = frontend / "index.html"
    assets = frontend / "assets"
    if not html.is_file() or not assets.is_dir():
        return False
    return any(assets.glob("*.js")) and any(assets.glob("*.css"))
