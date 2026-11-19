"""Stage 2: each receipt is approved by merchant before reward QR unlocks.

This isolated in-memory test stubs the *already verified review guard* only,
because cryptographic code review is covered by separate v0.6.10 tests.
It never bypasses that guard in the application.
"""
from types import SimpleNamespace
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from business.db import Base
from business.models import Merchant,Store,Program,Membership,ReceiptClaim,Reward
from business import main as business_main, pilot_v06, pilot_readiness_v069, wallet_reads_v068

@pytest.fixture
def basket(monkeypatch):
    monkeypatch.setattr(pilot_readiness_v069,'require_reward_schema',lambda db:None)
    monkeypatch.setattr(pilot_v06,'approval_guard',lambda db,claim,staff:None)
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        merchant=Merchant(name='Bistro',status='active')
        db.add(merchant);db.flush()
        store=Store(merchant_id=merchant.id,name='City',address='Bucharest',
                    latitude=44.4,longitude=26.1,active=True)
        db.add(store);db.flush()
        program=Program(merchant_id=merchant.id,store_id=store.id,
            title='Three verified bills',description='',stamps_required=3,
            min_purchase_minor=1500,reward_minor=2000,
            status='published',currency='RON')
        db.add(program);db.flush()
        member=Membership(consumer_id='member-A',program_id=program.id,stamps=0)
        other=Membership(consumer_id='member-B',program_id=program.id,stamps=0)
        db.add_all([member,other])
        claims=[]
        for i in range(3):
            claim=ReceiptClaim(merchant_id=merchant.id,program_id=program.id,
                consumer_id='member-A',external_receipt_id='signed-receipt-'+str(i),
                amount_minor=3000,status='pending',source_system='pruvs')
            claims.append(claim)
        db.add_all(claims);db.commit()
        yield db,program,member,other,claims,SimpleNamespace(merchant_id=merchant.id,role='owner')
    engine.dispose()

def test_three_approved_receipts_create_one_wallet_reward_only_at_threshold(basket):
    db,program,member,other,claims,staff=basket
    for index,claim in enumerate(claims):
        assert wallet_reads_v068.reward_rows(db,'member-A')==[]
        assert wallet_reads_v068.reward_rows(db,'member-B')==[]
        result=business_main.approve_claim(claim.id,staff=staff,db=db)
        assert result['status']=='approved'
        assert result['reward_awarded'] is (index==2)
        if index<2:
            assert result['stamps']==index+1
            assert wallet_reads_v068.reward_rows(db,'member-A')==[]
        else:
            assert result['stamps']==0  # 3 stamps exchanged for one reward
            rewards=wallet_reads_v068.reward_rows(db,'member-A')
            assert len(rewards)==1
            assert rewards[0]['status']=='available'
            assert rewards[0]['code'] is None  # QR requires explicit authenticated reserve
    assert wallet_reads_v068.reward_rows(db,'member-B')==[]
    assert wallet_reads_v068.membership_rows(db,'member-B')[0]['stamps']==0
    assert len(db.scalars(select(Reward).where(Reward.consumer_id=='member-A')).all())==1
    with pytest.raises(HTTPException) as exc:
        business_main.approve_claim(claims[2].id,staff=staff,db=db)
    assert exc.value.status_code==409
    assert len(wallet_reads_v068.reward_rows(db,'member-A'))==1

def test_customer_cannot_unblock_wallet_by_claiming_without_review(basket):
    db,program,member,other,claims,staff=basket
    assert all(claim.status=='pending' for claim in claims)
    assert member.stamps==0
    assert wallet_reads_v068.reward_rows(db,'member-A')==[]

def test_bill_selection_and_payment_confirmation_remain_separate():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    source=(root/'frontend/src/Bill.jsx').read_text()
    assert 'selection/complete' in source
    assert 'chooseSection(\'summary\')' in source
    assert 'Payment confirmation' in source
    assert 'payment' not in source.split('async function nextToSummary() {',1)[1].split('async function select(',1)[0].split('setData(await send(',1)[1].split(');',1)[0]
