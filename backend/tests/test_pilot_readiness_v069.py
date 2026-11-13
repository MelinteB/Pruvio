"""v0.6.9 staging-only receipt readiness and legacy redemption tests."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from business import pilot_readiness_v069 as readiness

REPO = Path(__file__).resolve().parents[1]


def test_only_fully_configured_merchant_reports_ready():
    schema = {'campaign_media': True, 'customer_codes': True,
              'discount_reconciliation': True}
    ready = readiness.summarize_readiness(
        schema, receipts_enabled=True, codes_enabled=True,
        merchant_allowed=True, evidence_required=True)
    assert ready['status'] == 'ready'
    assert ready['receipt_review_ready'] is True
    assert ready['blocked_by'] == []


def test_missing_migrations_and_flags_are_explicit_not_empty_wallet():
    report = readiness.summarize_readiness(
        {'campaign_media': False, 'customer_codes': True,
         'discount_reconciliation': False},
        receipts_enabled=True, codes_enabled=True,
        merchant_allowed=False, evidence_required=False)
    assert report['receipt_review_ready'] is False
    assert 'merchant_allowlisted' in report['blocked_by']
    assert 'reward_reconciliation_migrated' in report['blocked_by']
    assert 'consented_receipt_review_required' in report['blocked_by']
    assert 'campaign_media_migrated' in report['blocked_by']
    assert 'database_url' not in repr(report).lower()


def test_missing_discount_schema_fails_closed_before_writing(monkeypatch):
    monkeypatch.setattr(readiness, 'check_schema',
                        lambda connection: {'discount_reconciliation': False})
    fake_db = SimpleNamespace(connection=lambda: object())
    with pytest.raises(HTTPException) as exc:
        readiness.require_reward_schema(fake_db)
    assert exc.value.status_code == 503
    assert 'migration' in exc.value.detail.lower()


def test_schema_check_exception_still_blocks_reward_mutation(monkeypatch):
    def fail(_):
        raise ConnectionError('staging db offline')
    monkeypatch.setattr(readiness, 'check_schema', fail)
    with pytest.raises(HTTPException) as exc:
        readiness.require_reward_schema(SimpleNamespace(connection=lambda: object()))
    assert exc.value.status_code == 503
    assert 'staging db offline' not in exc.value.detail


def test_legacy_reward_confirmation_cannot_bypass_sale_audit():
    source = (REPO / 'business/main.py').read_text(encoding='utf-8')
    start = source.index("def confirm_reward(")
    end = source.index("@app.post('/v1/merchant/campaign-suggestions')", start)
    old = source[start:end]
    assert "raise HTTPException(409,'Legacy confirmation is disabled." in old
    assert "reward.status='redeemed'" not in old
    # The audited sale-reference route remains available.
    assert "def confirm_redemption_code(" in source
    assert "require_reward_schema(db)" in source
