#!/usr/bin/env python3
"""Read-only, offline Pruvs launch evidence inventory (NOT launch approval).

Does not open databases, authenticate to providers, delete data, or certify GDPR.
Evidence references, reviewer names, file paths and environment secrets are never
included in its report. Keep populated evidence outside Git.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re

from retention_review import review as review_retention

EVIDENCE_ITEMS = (
    'controller_and_legal_text',
    'processor_and_transfer_review',
    'retention_and_legal_holds',
    'postgresql_isolated_restore',
    'receipt_cloud_recovery_and_deletion',
    'account_deletion_and_data_export',
    'cross_user_authorization',
    'ocr_credit_and_duplicate_safety',
    'stripe_live_or_explicitly_disabled',
    'incident_and_support_procedures',
)
PLACEHOLDER_MARKERS = (
    '[LEGAL ENTITY NAME]', '[CONTACT EMAIL]', '[REGISTERED ADDRESS]',
    'This prototype does not yet define final retention periods',
    'final governing-law and jurisdiction clause must be completed',
    'placeholders until the operating legal entity is finalized',
    'draft-2026-', '— Draft', '[INSERT', 'TODO', 'TBD',
)
REQUIRED_METADATA = ('reference', 'reviewer_role', 'reviewed_at')


def legal_source_state(path: Path) -> str:
    """Detect known draft wording without importing potentially dynamic legal code."""
    try:
        if not path.is_file() or path.is_symlink():
            return 'source_missing'
        if path.stat().st_size > 256_000:
            return 'source_unreadable'
        content = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return 'source_unreadable'
    if not content.strip():
        return 'source_empty'
    if (any(marker.casefold() in content.casefold() for marker in PLACEHOLDER_MARKERS)
            or re.search(r'\bdraft-\d{4}-\d{2}-\d{2}\b', content, re.I)):
        return 'draft_content'
    # Text-only presence never proves that documents were approved or published.
    return 'text_needs_human_review'


def _recorded(item: object, today: date) -> bool:
    if not isinstance(item, dict) or item.get('decision') != 'verified':
        return False
    for field in REQUIRED_METADATA:
        value = item.get(field)
        if (not isinstance(value, str) or not value.strip() or len(value) > 180
                or value.strip().casefold() in ('todo', 'tbd', 'pending', 'draft', 'example', 'unknown')):
            return False
    # Require ISO calendar date, not an unchecked string or a future attestation.
    stamp = item['reviewed_at']
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', stamp):
        return False
    try:
        reviewed = date.fromisoformat(stamp)
    except ValueError:
        return False
    return reviewed <= today and (today - reviewed).days <= 365


def evidence_state(path: Path | None, *, today: date | None = None) -> dict:
    """Return only safe completion metadata; never report reference contents."""
    today = today or datetime.now(timezone.utc).date()
    results = {'present': False, 'recorded': [], 'missing_or_incomplete': list(EVIDENCE_ITEMS)}
    if path is None or not path.is_file() or path.is_symlink():
        return results
    try:
        if path.stat().st_size > 128_000:
            return results
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        return results
    if not isinstance(raw, dict) or raw.get('schema_version') != 1 or not isinstance(raw.get('evidence'), dict):
        return results
    results['present'] = True
    results['recorded'] = [k for k in EVIDENCE_ITEMS if _recorded(raw['evidence'].get(k), today)]
    results['missing_or_incomplete'] = [k for k in EVIDENCE_ITEMS if k not in results['recorded']]
    return results


def retention_state(path: Path) -> dict:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 256_000:
            raise ValueError('Unsafe retention file')
        state = review_retention(path)
        raw = json.loads(path.read_text(encoding='utf-8'))
        # A filled-in placeholder like 'TBD' must not count as a retention decision.
        entries = raw.get('categories', {})
        placeholder_rows = sum(
            isinstance(row, dict) and any(
                isinstance(row.get(field), str) and row[field].strip().casefold()
                in ('tbd', 'todo', 'pending', 'draft', 'example', 'unknown')
                for field in ('purpose', 'lawful_basis', 'retention_rule',
                              'deletion_method', 'reviewer_approval'))
            for row in entries.values()
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return {'status': 'worksheet_missing_or_invalid', 'expected': 12, 'incomplete': 12}
    return {
        'status': ('manual_review_required' if placeholder_rows
                   else state['status']),
        'expected': state['categories_expected'],
        'incomplete': len(state['categories_missing']) + len(state['categories_incomplete']) + placeholder_rows,
    }


def audit(backend: Path, *, retention_policy: Path | None = None,
          evidence_file: Path | None = None, today: date | None = None) -> dict:
    """Offline launch checklist: findings are not independent verification."""
    backend = Path(backend).resolve()
    if not (backend / 'app/main.py').is_file():
        raise ValueError('Not a Pruvs backend directory')
    retention_policy = retention_policy or backend / 'config/retention-policy.example.json'
    legal = legal_source_state(backend / 'app/legal_content.py')
    retention = retention_state(retention_policy)
    evidence = evidence_state(evidence_file, today=today)
    blocking = (
        legal != 'text_needs_human_review'
        or retention['status'] != 'review_entries_complete'
        or bool(evidence['missing_or_incomplete'])
    )
    return {
        'status': 'incomplete' if blocking else 'evidence_recorded_pending_independent_validation',
        'legal_text': legal,
        'retention': retention,
        'evidence': evidence,
        'database_or_cloud_accessed': False,
        'deletion_performed': False,
        'approval_granted': False,
        'note': 'Metadata coverage only. Human legal/security approval, live tests and independent evidence review remain required.',
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True, type=Path)
    parser.add_argument('--retention-policy', type=Path, default=None)
    parser.add_argument('--evidence', type=Path, default=None)
    parser.add_argument('--strict', action='store_true', help='Fail if documentation/evidence is incomplete')
    args = parser.parse_args(argv)
    try:
        result = audit(args.backend, retention_policy=args.retention_policy,
                       evidence_file=args.evidence)
    except (OSError, ValueError, TypeError):
        print('STOP: Invalid backend or unreadable audit input (details withheld).')
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if args.strict and result['status'] == 'incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
