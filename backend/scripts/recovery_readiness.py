#!/usr/bin/env python3
"""Read-only PostgreSQL custom-format backup integrity check.

Never connects to a database, runs pg_restore --list only (not a restore), or
accesses the production DB URL. A real isolated restore remains mandatory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def inspect_backup(path: Path, expected_sha256: str, *, check_toc=False, pg_restore='pg_restore') -> dict:
    """Verify nonempty PGDMP header, complete SHA256, and optionally a readable TOC."""
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('Expected SHA-256 must contain exactly 64 hexadecimal characters.')
    if not path.is_file():
        raise ValueError('Backup file does not exist.')
    size = path.stat().st_size
    if size < 6:
        raise ValueError('Backup is empty or truncated.')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        if source.read(5) != b'PGDMP':
            raise ValueError('Backup is not a PostgreSQL custom-format dump (PGDMP).')
        source.seek(0)
        for part in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(part)
    actual = digest.hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise ValueError('Backup SHA-256 does not match the independently recorded digest.')
    result = {'format': 'postgresql-custom', 'bytes': size, 'sha256_verified': True,
              'toc_verified': False, 'isolated_restore_verified': False}
    if check_toc:
        executable = shutil.which(pg_restore)
        if not executable:
            raise ValueError('pg_restore is not installed. PostgreSQL TOC verification unavailable.')
        try:
            # Only -l: list contents without database access or execution.
            completed = subprocess.run([executable, '--list', str(path)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       timeout=90, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('pg_restore TOC verification timed out.') from exc
        if completed.returncode != 0 or not completed.stdout.strip():
            raise ValueError('pg_restore could not read the custom dump table of contents.')
        result['toc_verified'] = True
    return result


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--backup', type=Path, required=True, help='Path to a local, access-controlled pg_dump -Fc file')
    cli.add_argument('--sha256', required=True, help='An independently recorded SHA-256 hash')
    cli.add_argument('--check-toc', action='store_true', help='Check pg_restore --list, WITHOUT restoring')
    options = cli.parse_args(argv)
    try:
        status = inspect_backup(options.backup, options.sha256, check_toc=options.check_toc)
    except (ValueError, OSError) as exc:
        cli.exit(1, 'STOP: ' + str(exc) + '\n')
    print(json.dumps(status, indent=2))
    print('MANUAL REQUIRED: Restore into an isolated PostgreSQL database and verify application queries.')
    print('No database was accessed or restored by this command.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
