#!/usr/bin/env python3
"""Offline retention decision inventory; read-only, no DB access or automatic deletion.

This is NOT a retention scheduler and does not approve a policy. A legal/privacy
reviewer must document purposes, periods, lawful bases, and legal holds.
"""
import argparse
import json
from pathlib import Path

CATEGORIES = (
    'accounts_and_contact',
    'receipt_originals_and_ocr',
    'receipt_items_and_corrections',
    'shared_bills_and_participants',
    'payment_confirmations',
    'password_reset_and_otp',
    'sessions_passkeys_and_devices',
    'push_and_inbox_events',
    'stripe_billing_and_invoices',
    'security_admin_and_access_logs',
    'backups_and_restore_copies',
    'support_and_dispute_requests',
)


def review(path: Path) -> dict:
    """Report coverage, never erase data and never guess a retention duration."""
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not isinstance(payload.get('categories'), dict):
        raise ValueError('Invalid policy-review JSON structure.')
    missing = []
    incomplete = []
    for category in CATEGORIES:
        record = payload['categories'].get(category)
        if not isinstance(record, dict):
            missing.append(category)
        elif not all(isinstance(record.get(k), str) and record[k].strip()
                     for k in ('purpose', 'lawful_basis', 'retention_rule', 'deletion_method', 'reviewer_approval')):
            incomplete.append(category)
    return {
        'status': 'manual_review_required' if missing or incomplete else 'review_entries_complete',
        'categories_expected': len(CATEGORIES),
        'categories_missing': missing,
        'categories_incomplete': incomplete,
        'automatic_deletion_enabled': False,
        'notice': 'Completing a worksheet does not constitute legal approval or activate deletion.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Pruvs read-only retention policy worksheet check.')
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--strict', action='store_true', help='Return nonzero for incomplete decisions.')
    args = parser.parse_args(argv)
    try:
        result = review(args.policy.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print('ERROR: Cannot read the retention worksheet (' + type(exc).__name__ + ').')
        return 2
    print(json.dumps(result, indent=2))
    return 2 if args.strict and result['status'] != 'review_entries_complete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
