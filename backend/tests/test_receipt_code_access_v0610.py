"""Pruvs Business v0.6.10 claim-code access and merchant review regressions.

No real database, network, credentials or customer receipt is used.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from business import pilot_v06, pilot_v12
from business.models import utcnow
from business.models_v06 import ReceiptEvidence
from business.models_v12 import CustomerClaimCode
from business.receipt_claim_access_v0610 import claim_access_flags, code_is_unlocked


NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def code(staff='s1', age_minutes=2):
    return SimpleNamespace(
        merchant_id='m1',
        unlocked_by_staff=staff,
        unlocked_at=NOW-timedelta(minutes=age_minutes),
    )


def test_customer_code_unlock_is_staff_scoped_and_time_limited():
    assert code_is_unlocked(code(), 's1', now=NOW)
    assert not code_is_unlocked(code(), 's2', now=NOW)
    assert not code_is_unlocked(code(age_minutes=16), 's1', now=NOW)
    assert not code_is_unlocked(code(age_minutes=-2), 's1', now=NOW)
    assert not code_is_unlocked(SimpleNamespace(
        merchant_id='m1', unlocked_by_staff=None, unlocked_at=None), 's1', now=NOW)


def test_locked_claim_has_no_review_button_permission():
    flags = claim_access_flags(code('s2'), 's1', pending=True, now=NOW)
    assert flags == {'requires_customer_code': True, 'review_unlocked': False}
    assert claim_access_flags(code(), 's1', pending=True, now=NOW)['review_unlocked']
    assert not claim_access_flags(code(), 's1', pending=False, now=NOW)['review_unlocked']
    assert claim_access_flags(None, 's1', pending=True, now=NOW) == {
        'requires_customer_code': False, 'review_unlocked': True,
    }


def test_review_is_not_authorized_after_code_rotation(monkeypatch):
    old_view = SimpleNamespace(at=utcnow())
    stored = SimpleNamespace(merchant_id='m1', created_at=utcnow())
    claim = SimpleNamespace(id='claim1', source_system='pruvs')
    staff = SimpleNamespace(id='s1', merchant_id='m1')
    class FakeDB:
        def get(self, model, key):
            assert model is ReceiptEvidence and key == 'claim1'
            return stored
        def scalar(self, query):
            return old_view
        def add(self, item):
            pytest.fail('Decision must not be written if customer code was rotated')
    def invalidated(*_):
        raise HTTPException(403, 'Customer code was rotated')
    monkeypatch.setattr(pilot_v12, 'require_code_unlock', invalidated)
    with pytest.raises(HTTPException) as failure:
        pilot_v06.approval_guard(FakeDB(), claim, staff)
    assert failure.value.status_code == 403


def test_changed_receipt_evidence_cannot_be_reissued(monkeypatch):
    # Use the actual endpoint function, but a fake DB and signed-proof stub.
    raw = b'JPEG_TEST_BYTES'
    digest = hashlib.sha256(raw).hexdigest()
    current = SimpleNamespace(
        id='claim1',merchant_id='m1', consumer_id='user1',
        program_id='p'*36,status='pending',amount_minor=1000,
    )
    old_evidence = SimpleNamespace(
        image_sha256='f'*64, merchant_label='Cafe', receipt_date='2026-11-13',
    )
    code_row = SimpleNamespace(code_hash='oldhash',expires_at=NOW,
                               unlocked_by_staff='s1',unlocked_at=NOW)
    merchant = SimpleNamespace(id='m1', status='active')
    program = SimpleNamespace(id='p'*36, merchant_id='m1',status='published',
                              store_id='store1',currency='RON',min_purchase_minor=0)
    class FakeDB:
        def __init__(self):
            self.scanned=0
            self.commits=0
        def get(self, model, key):
            if model is pilot_v12.Program: return program
            if model is ReceiptEvidence: return old_evidence
            if model is CustomerClaimCode: return code_row
            raise AssertionError(f'unexpected table {model}')
        def scalar(self, q):
            self.scanned+=1
            return SimpleNamespace(id='membership') if self.scanned == 1 else current
        def commit(self): self.commits+=1
    monkeypatch.setattr(pilot_v12,'ready',lambda:None)
    monkeypatch.setattr(pilot_v12,'merchant_pilot_allowed',lambda mid:True)
    monkeypatch.setattr(pilot_v12,'safe_image',lambda _:raw)
    monkeypatch.setattr(pilot_v12,'get_settings',lambda:SimpleNamespace(pruvs_bridge_secret='unused'))
    monkeypatch.setattr(pilot_v12,'decode',lambda *args:{
        'sub':'user1','store_id':'store1','currency':'RON','consent':True,
        'amount_minor':1000,'receipt_id':'a'*64,
        'evidence_sha256':digest,'merchant_label':'Cafe','receipt_date':'2026-11-13',
    })
    payload=pilot_v12.CustomerClaimIn(
        program_id='p'*36,
        code_hash='b'*64,receipt_proof='x'*100,
        evidence=pilot_v12.EvidenceIn(
            consent=True, merchant_label='Cafe',
            receipt_date='2026-11-13',image_base64='a'*600,
        ),
    )
    db=FakeDB()
    with pytest.raises(HTTPException) as exc:
        pilot_v12.create_customer_code(payload,consumer_id='user1',db=db)
    assert exc.value.status_code == 409
    assert db.commits == 0
    assert code_row.code_hash == 'oldhash'
    assert code_row.unlocked_by_staff == 's1'
