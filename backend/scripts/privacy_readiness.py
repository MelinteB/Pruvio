#!/usr/bin/env python3
"""Read-only launch/privacy review. Never prints environment secrets or queries user data.

Flags evidence that needs human verification; it cannot certify GDPR compliance,
backup integrity, legal terms, hosting configuration, or data deletion semantics.
"""
import argparse
import os
from pathlib import Path

PLACEHOLDERS = (
    'This prototype does not yet define final retention periods',
    'TODO',
    '[INSERT',
    'TBD',
)


def audit(backend, environment):
    messages = []
    legal = backend / 'app' / 'legal_content.py'
    if not legal.is_file():
        messages.append(('BLOCKER', 'Privacy/terms source is missing.'))
    elif any(term in legal.read_text(encoding='utf-8') for term in PLACEHOLDERS):
        messages.append(('BLOCKER', 'Privacy/terms contain placeholder or unfinished retention content; approve a real policy before launch.'))
    else:
        messages.append(('MANUAL', 'Legal and retention language requires professional review; text presence is not approval.'))

    dburl = environment.get('DATABASE_URL', '').strip().lower()
    if dburl.startswith(('postgresql://', 'postgresql+psycopg://', 'postgresql+psycopg2://', 'postgres://')):
        messages.append(('OK', 'PostgreSQL URL configured (value withheld); backup/restore still requires verification.'))
    else:
        messages.append(('MANUAL', 'PostgreSQL production configuration could not be confirmed from this shell.'))

    base = environment.get('PUBLIC_BASE_URL', '')
    if base.startswith('https://'):
        messages.append(('OK', 'Public base URL uses HTTPS (value withheld).'))
    else:
        messages.append(('MANUAL', 'Public HTTPS base URL could not be verified locally.'))

    if environment.get('PRUVS_REQUIRE_POSTGRES', '').lower() in ('1', 'true', 'yes'):
        messages.append(('OK', 'Production PostgreSQL startup guard opted in.'))
    else:
        messages.append(('MANUAL', 'Consider enabling PRUVS_REQUIRE_POSTGRES after confirming the Render database.'))

    if environment.get('PRUVS_REQUIRE_BUILD_MATCH', '').lower() in ('1', 'true', 'yes'):
        messages.append(('OK', 'Frontend/backend startup build check opted in.'))
    else:
        messages.append(('MANUAL', 'Consider PRUVS_REQUIRE_BUILD_MATCH after validating the Render build.'))

    if not (backend / 'app/react_app/data_export.py').is_file():
        messages.append(('BLOCKER', 'Account activity export module missing.'))
    else:
        messages.append(('OK', 'Authenticated scoped account activity export source present; permission tests still required.'))

    messages.extend([
        ('MANUAL', 'Verify restore of a production database backup into an isolated environment.'),
        ('MANUAL', 'Approve documented retention/deletion periods for receipts, logs, OTP, billing and payment audit records.'),
        ('MANUAL', 'Test full account and cloud-receipt deletion across all configured storage services.'),
        ('MANUAL', 'Verify Stripe webhook idempotency, refund/downgrade lifecycle and user-to-user authorization.'),
        ('MANUAL', 'Check privacy notices, controller/processor contracts and production monitoring with the responsible reviewers.'),
    ])
    return messages


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only Pruvs launch/privacy preflight; never displays secrets.')
    parser.add_argument('--backend', required=True, type=Path)
    parser.add_argument('--strict', action='store_true', help='Exit nonzero if known blocking issues remain.')
    args = parser.parse_args(argv)
    backend = args.backend.resolve()
    if not (backend / 'app/main.py').is_file():
        parser.error('--backend must be the Pruvs backend directory')
    checks = audit(backend, os.environ)
    for level, message in checks:
        print(f'[{level}] {message}')
    blockers = sum(level == 'BLOCKER' for level, _ in checks)
    print(f'Known blockers: {blockers}; manual checks are not automatically certified.')
    return 2 if args.strict and blockers else 0


if __name__ == '__main__':
    raise SystemExit(main())
