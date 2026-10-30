"""Production release metadata and small resource-management helpers.

This module intentionally uses only Python standard-library dependencies so it
can be exercised without starting the Pruvs API, making network calls, or
opening the database.
"""
from __future__ import annotations
import os
from pathlib import Path

RELEASE = "7.1.37"

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
    """Validate current HTML references and release manifest, not stale stray bundles."""
    return frontend_build_report(frontend)['status'] == 'ready'


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


# v7.1.20 - Reliable production build identification and readiness.
# Use only metadata and file paths; never expose server environment or database URLs.
import hashlib
import json
import re

_ASSET_PATTERN = re.compile(r'["\'](/assets/[A-Za-z0-9_./-]+\.(?:js|css))["\']')


def frontend_build_report(frontend: Path, expected: str | None = None, verify_hashes: bool = False) -> dict:
    """Return a public-safe report of version/assets with concrete failure reasons.

    Normal readiness checks are lightweight (HTML+manifest+file existence only).
    The CLI can request full checksums; hashing JS/CSS on every /ready is avoided.
    """
    expected = expected or RELEASE
    problems = []
    html_path = frontend / 'index.html'
    manifest_path = frontend / 'build-manifest.json'
    html = ''
    manifest = {}
    try:
        html = html_path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        problems.append('missing_index')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError('Invalid manifest')
    except (OSError, ValueError, UnicodeError):
        problems.append('missing_or_invalid_manifest')
        manifest = {}
    build_version = manifest.get('version')
    if build_version != expected:
        problems.append('version_mismatch')
    refs = sorted(set(_ASSET_PATTERN.findall(html)))
    if not refs or not any(p.endswith('.js') for p in refs) or not any(p.endswith('.css') for p in refs):
        problems.append('missing_asset_references')
    manifest_assets = manifest.get('assets')
    if not isinstance(manifest_assets, dict):
        problems.append('invalid_asset_manifest')
        manifest_assets = {}
    for ref in refs:
        # HTML provides public URLs; never resolve arbitrary/supplied path segments.
        if '..' in Path(ref).parts:
            problems.append('unsafe_asset_path')
            continue
        asset = frontend / ref.lstrip('/')
        if not asset.is_file():
            problems.append('missing_asset')
            continue
        key = 'dist' + ref
        advertised = manifest_assets.get(key)
        if not isinstance(advertised, str) or not re.fullmatch(r'[0-9a-f]{64}', advertised):
            problems.append('asset_not_stamped')
            continue
        if verify_hashes and hashlib.sha256(asset.read_bytes()).hexdigest() != advertised:
            problems.append('asset_hash_mismatch')
    # Fingerprint the referenced assets and expected version, not timestamps/paths.
    fingerprint = hashlib.sha256(json.dumps({
        'version': build_version,
        'assets': {ref: manifest_assets.get('dist' + ref) for ref in refs},
    }, sort_keys=True).encode('utf-8')).hexdigest()[:16] if refs else None
    return {
        'status': 'ready' if not problems else 'mismatch',
        'version': expected,
        'build_version': build_version,
        'build_id': fingerprint,
        'assets': refs,
        'checks': sorted(set(problems)),
    }


def require_build_match_if_enabled(frontend: Path) -> None:
    """Optional fail-fast guard. Run only after npm run build on Render."""
    if os.getenv('PRUVS_REQUIRE_BUILD_MATCH', '').strip().lower() not in ('1', 'true', 'yes'):
        return
    report = frontend_build_report(frontend, verify_hashes=True)
    if report['status'] != 'ready':
        raise RuntimeError('Pruvs frontend build does not match backend release: ' + ', '.join(report['checks']))
