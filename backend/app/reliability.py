"""Production release metadata and small resource-management helpers.

This module intentionally uses only Python standard-library dependencies so it
can be exercised without starting the Pruvs API, making network calls, or
opening the database.
"""
from __future__ import annotations
import os
from pathlib import Path

RELEASE = "7.1.19"

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


# v7.1.19: bounded synchronous OCR uploads to protect the web worker pool.
# This is a per-process safeguard, not a durable job queue or cluster-wide limit.
import threading
from contextlib import contextmanager


def bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if minimum <= value <= maximum else default
    except (TypeError, ValueError, OverflowError):
        return default


class OCRBusy(Exception):
    """No OCR capacity is available; retry without charging the user."""


class OCRCapacity:
    """Non-blocking per-process admission gate for synchronous receipt OCR."""

    def __init__(self, maximum: int):
        if maximum < 1:
            raise ValueError('OCR capacity must be positive')
        self.maximum = maximum
        self._gate = threading.BoundedSemaphore(maximum)

    @contextmanager
    def admit(self):
        if not self._gate.acquire(blocking=False):
            raise OCRBusy('Receipt processing is busy. Try again shortly.')
        try:
            yield
        finally:
            self._gate.release()


ocr_capacity = OCRCapacity(bounded_integer('PRUVS_OCR_MAX_INFLIGHT', 2, 1, 8))
