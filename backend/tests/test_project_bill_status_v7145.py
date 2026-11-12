"""Pure lifecycle regression. No database access required."""
from types import SimpleNamespace
from app.services.project_bill_state_v7145 import split_state, project_share_state


def share(user, payer, status, cents=500):
    return SimpleNamespace(user_id=user, paid_by_user_id=payer, payment_status=status, amount_minor=cents)


def test_new_receipt_is_unallocated():
    assert project_share_state([])=='unallocated'


def test_allocation_not_treated_as_payment():
    assert project_share_state([share(1,1,'confirmed'), share(2,1,'unpaid')])=='allocated'
    assert project_share_state([share(1,1,'confirmed'), share(2,1,'reported')])=='allocated'


def test_confirmed_payment_is_distinct():
    assert project_share_state([share(1,1,'confirmed'), share(2,1,'confirmed')])=='confirmed'


def test_owner_only_share_does_not_create_external_debt():
    assert project_share_state([share(1,1,'confirmed')])=='confirmed'


def test_split_remaining_blocks_confirmation():
    participants=[{'user_id':2,'total':50.0,'payment_status':'received'}]
    assert split_state(0.01,participants,1)=='unallocated'


def test_closed_allocation_not_confirmed_without_receipt():
    participants=[{'user_id':1,'total':10,'payment_status':'unpaid'},
                  {'user_id':2,'total':50,'payment_status':'paid'}]
    assert split_state(0,participants,1)=='allocated'


def test_split_confirmed_only_after_recipient_confirmation():
    participants=[{'user_id':1,'total':10,'payment_status':'unpaid'},
                  {'user_id':2,'total':50,'payment_status':'received'}]
    assert split_state(0,participants,1)=='confirmed'


def test_split_with_no_members_never_confirmed():
    assert split_state(0,[],1)=='unallocated'
