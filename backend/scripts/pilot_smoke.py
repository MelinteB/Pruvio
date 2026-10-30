#!/usr/bin/env python3
"""Pruvs v7.1.38: opt-in, unauthenticated, read-only deployment smoke checks.

Only sends GET requests to a fixed Pruvs host (or explicitly allowed loopback).
Never logs or accepts cookies, bill tokens, passwords or personal account data.
This does NOT replace authenticated end-to-end, storage, payment or legal tests.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

EXPECTED_VERSION = '7.1.38'
MAX_BODY_BYTES = 16_384
PUBLIC_ORIGINS = {'https://pruvs.io'}
PROTECTED_ROUTES = (
    '/api/v1/me',
    '/api/v1/history',
    '/api/v1/account/delete/preview',
    '/api/v1/receipts/2147483647',
    '/api/v1/bills/pruvs_pilot_not_a_real_bill',
    '/api/v1/inbox',
)


class SmokeError(ValueError):
    pass


def validate_origin(base_url: str, allow_local: bool = False) -> str:
    """Prevent accidental probes of external websites, internal services or paths."""
    if not isinstance(base_url, str) or len(base_url) > 200:
        raise SmokeError('Invalid deployment URL.')
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise SmokeError('Expected an origin, not credentials, query or a path.')
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        raise SmokeError('Expected a valid HTTP(S) origin.')
    origin = f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')
    if origin in PUBLIC_ORIGINS:
        return origin
    if allow_local and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost') and (parsed.port is None or 1024 <= parsed.port <= 65535):
        return origin
    raise SmokeError('Only https://pruvs.io is supported; use --allow-local for an explicit loopback URL.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def request_get(origin: str, path: str, timeout=7) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(origin + path, headers={
        'User-Agent': 'PruvsPilotSmoke/7.1.38',
        'Accept': 'application/json',
        'Cache-Control': 'no-cache',
    }, method='GET')
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    try:
        status = response.status
        headers = {key.lower(): value for key, value in response.headers.items()}
        body = response.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise SmokeError('Unexpected oversized public endpoint response.')
        return status, headers, body
    finally:
        response.close()


def safe_json(body: bytes) -> dict:
    try:
        decoded = json.loads(body)
        return decoded if isinstance(decoded, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def run_checks(base_url: str, *, allow_local: bool = False, transport=request_get) -> list[tuple[str, bool]]:
    origin = validate_origin(base_url, allow_local=allow_local)
    results = []

    def check(name, passed):
        results.append((name, bool(passed)))

    # Requests intentionally contain no cookies, token-bearing paths or private data.
    health_code, health_headers, health_body = transport(origin, '/health')
    health = safe_json(health_body)
    check('Liveness is healthy on v7.1.38', health_code == 200 and health.get('status') == 'ok' and health.get('version') == EXPECTED_VERSION)
    check('Release header is current', health_headers.get('x-pruvs-release') == EXPECTED_VERSION)
    check('No-cache and nosniff headers', 'no-store' in health_headers.get('cache-control', '').lower() and health_headers.get('x-content-type-options') == 'nosniff')

    ready_code, _, ready_body = transport(origin, '/ready')
    ready = safe_json(ready_body)
    check('Database and frontend are ready', ready_code == 200 and ready.get('status') == 'ready' and ready.get('version') == EXPECTED_VERSION)

    release_code, _, release_body = transport(origin, '/api/v1/release')
    release = safe_json(release_body)
    check('Frontend release/build is ready', release_code == 200 and release.get('status') == 'ready' and release.get('version') == EXPECTED_VERSION and bool(re.fullmatch(r'[a-f0-9]{16}', str(release.get('build_id', '')))))

    config_code, _, config_body = transport(origin, '/api/v1/config')
    check('Public config matches release', config_code == 200 and safe_json(config_body).get('version') == EXPECTED_VERSION)

    for path in PROTECTED_ROUTES:
        code, headers, _ = transport(origin, path)
        # These private endpoints must not leak data or redirect to a different origin.
        check('Unauthenticated access blocked: ' + path.split('/')[3] if len(path.split('/')) > 3 else 'Private API access blocked', code in (401, 403) and 'location' not in headers)
    return results


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='https://pruvs.io', help='Pruvs origin to inspect; never an account or bill URL')
    p.add_argument('--allow-local', action='store_true', help='Explicitly allow HTTP loopback testing only')
    args = p.parse_args(argv)
    try:
        origin = validate_origin(args.url, allow_local=args.allow_local)
        print('Pruvs pilot smoke checks (unauthenticated, GET-only):', origin)
        checks = run_checks(origin, allow_local=args.allow_local)
    except (SmokeError, urllib.error.URLError, OSError, TimeoutError, UnicodeError, ValueError) as exc:
        print('STOP: Pilot smoke checks unavailable:', type(exc).__name__, file=sys.stderr)
        return 2
    for description, ok in checks:
        print(('PASS' if ok else 'FAIL') + ': ' + description)
    total = len(checks)
    passed = sum(ok for _, ok in checks)
    print(f'RESULT: {passed}/{total} checks passed. No user records, auth cookies, payments or receipts accessed.')
    print('Authenticated test-account journeys, real cloud/OCR, backup restore and legal approval remain separate.')
    return 0 if passed == total else 2


if __name__ == '__main__':
    raise SystemExit(main())
