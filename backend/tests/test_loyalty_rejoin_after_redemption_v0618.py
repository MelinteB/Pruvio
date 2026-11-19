"""End-to-end isolated DB regression for reusable loyalty cycles.

A redeemed one-use voucher is *not* reused. The next cycle starts only
after a fresh customer join, and only if no stamps, pending receipt review
or unredeemed vouchers remain. All redemption ledger rows are retained.
"""
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from business.db import Base
from business import main
from business.models import (Merchant, Staff, Store, Program, Membership,
                             Reward, ReceiptClaim, utcnow)
from business.models_v067 import DiscountRedemption
from business.loyalty_cycles_v0618 import close_completed_cycle


@pytest.fixture
def scenario():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine,autoflush=False,expire_on_commit=False) as db:
        merchant=Merchant(name='Cafe',status='active')
        db.add(merchant);db.flush()
        staff=Staff(merchant_id=merchant.id,email='owner@example.test',
                    password_hash='unused',role='owner',active=True)
        store=Store(merchant_id=merchant.id,name='Cafe',address='',
                    latitude=44.4,longitude=26.1)
        db.add_all([staff,store]);db.flush()
        program=Program(merchant_id=merchant.id,store_id=store.id,
                        title='3 coffees',description='Three visits',
                        stamps_required=3,min_purchase_minor=100,
                        reward_minor=500,currency='RON',status='published')
        db.add(program);db.flush()
        customer='test-consumer-1'
        member=Membership(consumer_id=customer,program_id=program.id,stamps=0)
        reward=Reward(merchant_id=merchant.id,program_id=program.id,
                      consumer_id=customer,status='reserved',
                      redemption_code='DEADBEEF2026',
                      reserved_until=utcnow()+timedelta(minutes=5))
        db.add_all([member,reward]);db.commit()
        yield db,staff,program,member,reward,customer
    engine.dispose()


def confirm(db,staff,code='DEADBEEF2026'):
    return main.confirm_redemption_code(
      main.RedemptionSaleIn(code=code,sale_reference='paid-in-shop-112',
                            sale_amount_minor=1999),
      staff=staff,db=db)


def test_redeeming_last_voucher_reopens_join_without_losing_history(scenario):
    db,staff,program,member,reward,customer=scenario
    result=confirm(db,staff)
    assert result['status']=='redeemed'
    assert result['can_join_again'] is True
    assert db.get(Membership,member.id) is None
    assert db.get(Reward,reward.id).status=='redeemed'
    ledger=db.scalar(select(DiscountRedemption).where(DiscountRedemption.reward_id==reward.id))
    assert ledger and ledger.sale_reference=='paid-in-shop-112'
    assert main.customer_memberships(consumer_id=customer,db=db)['memberships']==[]
    new_join=main.join_program(program.id,consumer_id=customer,db=db)
    assert new_join['already_joined'] is False
    assert new_join['stamps']==0
    again=main.join_program(program.id,consumer_id=customer,db=db)
    assert again['already_joined'] is True
    assert db.get(Reward,reward.id).status=='redeemed'


def test_new_join_is_scoped_to_same_customer_and_program(scenario):
    db,staff,program,member,reward,customer=scenario
    confirm(db,staff)
    assert main.customer_memberships(consumer_id='another-user',db=db)['memberships']==[]
    main.join_program(program.id,consumer_id=customer,db=db)
    assert len(main.customer_memberships(consumer_id=customer,db=db)['memberships'])==1
    assert main.customer_memberships(consumer_id='another-user',db=db)['memberships']==[]


@pytest.mark.parametrize('blocker',('stamps','pending','available','reserved'))
def test_redemption_does_not_forfeit_other_active_entitlements(scenario,blocker):
    db,staff,program,member,reward,customer=scenario
    if blocker=='stamps':
        member.stamps=1
    elif blocker=='pending':
        db.add(ReceiptClaim(merchant_id=staff.merchant_id,program_id=program.id,
          consumer_id=customer,source_system='pruvs',external_receipt_id='r-pending',
          amount_minor=1200,status='pending'))
    else:
        db.add(Reward(merchant_id=staff.merchant_id,program_id=program.id,
          consumer_id=customer,status=blocker))
    db.commit()
    result=confirm(db,staff)
    assert result['can_join_again'] is False
    assert db.get(Membership,member.id) is not None


def test_double_redemption_cannot_start_another_cycle(scenario):
    db,staff,program,member,reward,customer=scenario
    confirm(db,staff)
    with pytest.raises(HTTPException) as err:
        confirm(db,staff)
    assert err.value.status_code==409
    assert db.scalar(select(DiscountRedemption).where(DiscountRedemption.reward_id==reward.id))


def test_cycle_cleanup_requires_a_membership(scenario):
    db,staff,program,member,reward,customer=scenario
    db.delete(member);db.flush()
    assert close_completed_cycle(db,consumer_id=customer,program_id=program.id) is False
