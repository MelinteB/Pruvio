"""Current-version regression tests: leave forfeiture and all-or-nothing QR packages."""
import base64
import hashlib
import io
from datetime import timedelta
from pathlib import Path

import jwt
import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.react_app.loyalty_gateway import pseudonym
from business.db import Base
from business.models import Merchant, Staff, Store, Program, Membership, ReceiptClaim, Reward, utcnow
from business.models_v06 import ReceiptEvidence, ReceiptEvidenceAccess
from business.models_v12 import CustomerClaimCode
from business import main as business_main
from business import pilot_v06, pilot_v12
from business import receipt_packages_v0618 as packages


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(packages, 'require_reward_schema', lambda db: None)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        merchant = Merchant(name='Coffee test merchant', status='active')
        db.add(merchant)
        db.flush()
        staff = Staff(merchant_id=merchant.id, email='owner@example.test',
                      password_hash='x', role='owner', active=True)
        store = Store(merchant_id=merchant.id, name='Downtown',
                      address='Bucharest', latitude=44.43, longitude=26.10, active=True)
        db.add_all([staff, store])
        db.flush()
        program = Program(merchant_id=merchant.id, store_id=store.id,
                          title='Three verified receipts', description='',
                          stamps_required=3, min_purchase_minor=1000,
                          reward_minor=1500, currency='RON', status='published')
        db.add(program)
        db.flush()
        member = Membership(consumer_id='consumer-A-123456789abcdef01234567890', program_id=program.id, stamps=0)
        db.add(member)
        db.commit()
        yield db, merchant, staff, program, member
    engine.dispose()


def insert_receipts(db, merchant, staff, program, count=3):
    claims = []
    now = utcnow()
    for n in range(count):
        claim = ReceiptClaim(merchant_id=merchant.id, program_id=program.id,
                             consumer_id='consumer-A-123456789abcdef01234567890', external_receipt_id='signed-'+str(n),
                             source_system='pruvs', amount_minor=2500, status='pending')
        db.add(claim)
        db.flush()
        db.add(ReceiptEvidence(
            claim_id=claim.id, merchant_id=merchant.id, merchant_label='Coffee test merchant',
            receipt_date='2026-11-19',
            image_jpeg=b'\xff\xd8\xff'+b'x'*500+b'\xff\xd9',
            image_sha256='a'*64
        ))
        unlocked_at=now-timedelta(minutes=2)
        db.add(CustomerClaimCode(
            claim_id=claim.id, merchant_id=merchant.id,
            code_hash=(str(n+1)*64), expires_at=now+timedelta(minutes=10),
            unlocked_by_staff=staff.id, unlocked_at=unlocked_at
        ))
        db.add(ReceiptEvidenceAccess(
            claim_id=claim.id, staff_id=staff.id, merchant_id=merchant.id,
            action='view', at=now-timedelta(minutes=1)
        ))
        claims.append(claim)
    db.commit()
    return claims


@pytest.fixture
def signed_receipts(context, monkeypatch):
    db, merchant, staff, program, member = context
    monkeypatch.setenv('PRUVS_BUSINESS_RECEIPT_PILOT_ENABLED', 'true')
    monkeypatch.setenv('PRUVS_BUSINESS_CUSTOMER_CODES_V12_ENABLED', 'true')
    monkeypatch.setenv('PRUVS_BUSINESS_PILOT_DB_ENROLLMENT_ENABLED', 'false')
    monkeypatch.setenv('PRUVS_BUSINESS_V06_PILOT_MERCHANT_IDS', merchant.id)
    secret = pilot_v12.get_settings().pruvs_bridge_secret
    user_id = 42
    member.consumer_id = pseudonym(secret, 'customer-v1', user_id)
    db.commit()

    image_buffer = io.BytesIO()
    Image.new('RGB', (100, 160), 'white').save(image_buffer, format='JPEG')
    image = image_buffer.getvalue()
    image_hash = hashlib.sha256(image).hexdigest()
    evidence = pilot_v12.EvidenceIn(
        consent=True, merchant_label=merchant.name, receipt_date='2026-11-19',
        image_base64=base64.b64encode(image).decode('ascii'),
    )

    def receipt(case_id):
        code = f'{case_id:024X}'
        now = utcnow()
        proof = jwt.encode({
            'iss': 'pruvs-core', 'aud': 'pruvs-business', 'typ': 'receipt_proof_v06',
            'sub': member.consumer_id, 'receipt_id': pseudonym(secret, 'receipt-v1', f'{user_id}:{case_id}'),
            'store_id': program.store_id, 'amount_minor': 2500, 'currency': 'RON',
            'consent': True, 'evidence_sha256': image_hash,
            'merchant_label': merchant.name, 'receipt_date': evidence.receipt_date,
            'iat': now, 'exp': now + timedelta(minutes=5), 'jti': f'test-claim-{case_id}',
        }, secret, algorithm='HS256')
        payload = pilot_v12.CustomerClaimIn(
            program_id=program.id,
            code_hash=hashlib.sha256(('v12:' + code).encode('ascii')).hexdigest(),
            receipt_proof=proof, evidence=evidence,
        )
        return code, payload

    return receipt


def test_new_receipt_cannot_be_submitted_after_original_membership_disappears(
        context, signed_receipts, monkeypatch):
    db, _, _, _, member = context
    _, payload = signed_receipts(1)
    consumer_id = member.consumer_id
    scalar = db.scalar

    def simulate_leave_before_lock(statement):
        sql = str(statement.compile(dialect=postgresql.dialect()))
        if 'FROM loyalty_memberships' in sql and 'FOR UPDATE' in sql:
            db.delete(member)
            db.flush()
        return scalar(statement)

    monkeypatch.setattr(db, 'scalar', simulate_leave_before_lock)
    with pytest.raises(HTTPException) as exc:
        pilot_v12.create_customer_code(payload, consumer_id=consumer_id, db=db)
    assert exc.value.status_code == 409
    assert db.scalars(select(ReceiptClaim)).all() == []


@pytest.mark.parametrize('unavailable', ['store', 'merchant', 'foreign_store'])
def test_stale_receipt_link_cannot_use_unavailable_program_location(
        context, signed_receipts, unavailable):
    db, merchant, _, program, member = context
    _, payload = signed_receipts(1)
    store = db.get(Store, program.store_id)
    if unavailable == 'store':
        store.active = False
    elif unavailable == 'merchant':
        merchant.status = 'paused'
    else:
        foreign_merchant = Merchant(name='Other merchant', status='active')
        db.add(foreign_merchant)
        db.flush()
        store.merchant_id = foreign_merchant.id
    db.commit()

    with pytest.raises(HTTPException) as eligibility:
        pilot_v12.eligible(program.id, consumer_id=member.consumer_id, db=db)
    assert eligibility.value.status_code == 409
    with pytest.raises(HTTPException) as submission:
        pilot_v12.create_customer_code(payload, consumer_id=member.consumer_id, db=db)
    assert submission.value.status_code == 409
    assert db.scalars(select(ReceiptClaim)).all() == []


def test_signed_receipts_require_capacity_and_each_staff_review_before_reward(
        context, signed_receipts):
    db, _, staff, program, member = context
    claim_ids = []
    for case_id in range(1, 4):
        code, payload = signed_receipts(case_id)
        claim = pilot_v12.create_customer_code(payload, consumer_id=member.consumer_id, db=db)
        claim_ids.append(claim['claim_id'])
        assert pilot_v12.lookup_customer_code(
            pilot_v12.CodeLookup(code=code), staff=staff, db=db
        )['claim_id'] == claim['claim_id']
        assert pilot_v06.merchant_evidence(claim['claim_id'], staff=staff, db=db).status_code == 200

    _, extra = signed_receipts(4)
    with pytest.raises(HTTPException) as exc:
        pilot_v12.create_customer_code(extra, consumer_id=member.consumer_id, db=db)
    assert exc.value.status_code == 409
    assert db.scalars(select(Reward)).all() == []

    result = packages.approve_receipt_package(
        packages.PackageApproval(program_id=program.id, consumer_id=member.consumer_id,
                                 claim_ids=claim_ids),
        staff=staff, db=db,
    )
    assert result['approved_receipts'] == 3
    assert result['reward_awarded']

    _, prior_receipt = signed_receipts(1)
    with pytest.raises(HTTPException) as exc:
        pilot_v12.create_customer_code(prior_receipt, consumer_id=member.consumer_id, db=db)
    assert exc.value.status_code == 409
    assert len(db.scalars(select(Reward)).all()) == 1


def test_leave_requires_consent_for_forfeiture_and_never_releases_receipt_identity(context):
    db, merchant, staff, program, member = context
    claims=insert_receipts(db, merchant, staff, program, count=1)
    member.stamps=1
    voucher=Reward(merchant_id=merchant.id, program_id=program.id,
                   consumer_id='consumer-A-123456789abcdef01234567890', status='reserved',
                   redemption_code='ABCD12345678', reserved_until=utcnow()+timedelta(minutes=5))
    db.add(voucher)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        business_main.leave_program(program.id, body=business_main.LeaveProgramIn(),
                                    consumer_id='consumer-A-123456789abcdef01234567890', db=db)
    assert exc.value.status_code==409
    result=business_main.leave_program(
        program.id, body=business_main.LeaveProgramIn(confirm_forfeit=True),
        consumer_id='consumer-A-123456789abcdef01234567890', db=db)
    assert result['left']
    assert result['forfeited']=={'stamps':1,'pending_receipts':1,'unused_rewards':1}
    assert db.get(Membership,member.id) is None
    assert db.get(ReceiptClaim,claims[0].id).status=='cancelled'
    assert db.get(Reward,voucher.id).status=='forfeited'
    assert db.get(Reward,voucher.id).redemption_code is None
    # Leaving does not delete an old claim or make the same receipt eligible elsewhere.
    db.add(ReceiptClaim(merchant_id=merchant.id, program_id=program.id,
                        consumer_id='consumer-A-123456789abcdef01234567890', source_system='pruvs',
                        external_receipt_id=claims[0].external_receipt_id,
                        amount_minor=2500,status='pending'))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    rejoined=business_main.join_program(program.id,consumer_id='consumer-A-123456789abcdef01234567890',db=db)
    assert rejoined['stamps']==0 and rejoined['already_joined'] is False


def test_merchant_approves_all_three_together_and_creates_single_reward(context):
    db, merchant, staff, program, member = context
    claims=insert_receipts(db, merchant, staff, program)
    found=packages.receipt_packages(staff=staff,db=db)
    assert len(found)==1
    assert found[0]['ready_to_approve'] is True
    assert len(found[0]['items'])==3
    payload=packages.PackageApproval(program_id=program.id,
                                      consumer_id='consumer-A-123456789abcdef01234567890',
                                      claim_ids=[c.id for c in claims])
    result=packages.approve_receipt_package(payload,staff=staff,db=db)
    assert result['approved_receipts']==3
    assert result['reward_awarded'] is True
    assert member.stamps==0
    assert [db.get(ReceiptClaim,c.id).status for c in claims]==['approved']*3
    rewards=db.scalars(select(Reward).where(Reward.program_id==program.id)).all()
    assert len(rewards)==1 and rewards[0].status=='available'
    with pytest.raises(HTTPException) as exc:
        packages.approve_receipt_package(payload,staff=staff,db=db)
    assert exc.value.status_code==409
    assert len(db.scalars(select(Reward)).all())==1


def test_one_unreviewed_or_rotated_qr_blocks_entire_package(context):
    db, merchant, staff, program, member = context
    claims=insert_receipts(db, merchant, staff, program)
    last=claims[-1]
    code=db.get(CustomerClaimCode,last.id)
    code.unlocked_at=utcnow()  # the previous evidence view predates the latest QR unlock
    db.commit()
    result=packages.receipt_packages(staff=staff,db=db)
    assert result[0]['ready_to_approve'] is False
    payload=packages.PackageApproval(program_id=program.id,
                                      consumer_id='consumer-A-123456789abcdef01234567890',
                                      claim_ids=[c.id for c in claims])
    with pytest.raises(HTTPException) as exc:
        packages.approve_receipt_package(payload,staff=staff,db=db)
    assert exc.value.status_code in (403,409)
    assert member.stamps==0
    assert all(db.get(ReceiptClaim,c.id).status=='pending' for c in claims)
    assert db.scalars(select(Reward)).all()==[]


def test_no_partial_package_and_no_single_receipt_shortcut(context,monkeypatch):
    db, merchant, staff, program, member = context
    claims=insert_receipts(db, merchant, staff, program)
    payload=packages.PackageApproval(
        program_id=program.id,consumer_id='consumer-A-123456789abcdef01234567890',
        claim_ids=[claims[0].id,claims[1].id])
    with pytest.raises(HTTPException) as exc:
        packages.approve_receipt_package(payload,staff=staff,db=db)
    assert exc.value.status_code==409
    from business import pilot_readiness_v069
    monkeypatch.setattr(pilot_readiness_v069,'require_reward_schema',lambda db:None)
    with pytest.raises(HTTPException) as exc:
        business_main.approve_claim(claims[0].id,staff=staff,db=db)
    assert exc.value.status_code==409
    assert member.stamps==0
    assert all(db.get(ReceiptClaim,c.id).status=='pending' for c in claims)


def test_customer_and_merchant_interfaces_expose_package_flow():
    root=Path(__file__).resolve().parents[1]
    customer=(root/'frontend/src/Rewards.jsx').read_text()
    business=(root/'business_frontend/src/ReceiptInbox.jsx').read_text()
    assert 'Receipts linked to this campaign' in customer
    assert 'confirm_forfeit:true' in customer
    assert 'CustomerReceiptCode' in customer
    assert 'Approve entire package' in business
    assert '/v1/merchant/claims/packages/approve' in business
