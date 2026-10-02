"""Regression coverage for Pruvs v6.5 split-bill/history/username changes."""

import pytest

from test_device_otp import db, delivery, user  # shared in-memory fixtures
from app.models.case import Case
from app.models.document import Document
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.models.split_bill_participant import SplitBillParticipant
from app.models.user import User
from app.services import onboarding_otp_service as otp
from app.services.split_bill_session_service import (
    close_split_bill_session,
    create_split_bill_session,
    get_owner_participant,
    get_split_bill_session_summary,
    join_split_bill_session_as_user,
    list_split_bill_sessions_for_user,
    record_participant_payment_status,
    reopen_split_bill_session,
    save_participant_selection,
    update_session_tip,
)
from app.services.username_service import username_base_from_name


def make_bill(db, owner, items, expected=2):
    case = Case(user_id=owner.id, module="split_bill", status="created")
    db.add(case)
    db.commit()
    document = Document(case_id=case.id, stored_filename="receipt.pdf", path="receipt.pdf")
    db.add(document)
    db.commit()
    rows = []
    for name, quantity, unit_price, total in items:
        row = ReceiptItem(
            case_id=case.id,
            document_id=document.id,
            name=name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total,
            currency="RON",
            source_language="en",
        )
        db.add(row)
        rows.append(row)
    db.commit()
    session = create_split_bill_session(db, case.id, owner.id, expected)
    return session, rows


def add_active_participant(db, suffix="guest"):
    account = User(
        username=f"{suffix}.user",
        username_key=f"{suffix}.user",
        name=f"{suffix.title()} User",
        email=f"{suffix}@example.com",
        phone_number=f"+4072{len(suffix):08d}"[-12:],
        status="active",
        is_email_verified=True,
    )
    # Use an explicitly unique Romanian-format number regardless of suffix length.
    account.phone_number = "+407" + str(200000000 + sum(ord(ch) for ch in suffix))[-8:]
    db.add(account)
    db.commit()
    return account


def test_remaining_quantity_can_be_claimed_by_next_participant(db):
    owner = user(db)
    session, (line,) = make_bill(db, owner, [("Sparkling water", 3, 10, 30)])
    guest = add_active_participant(db, "alice")
    joined = join_split_bill_session_as_user(db, session, guest)
    owner_participant = get_owner_participant(db, session)

    first = save_participant_selection(
        db, session, owner_participant.id, selected_quantities={line.id: 1}
    )
    row = first["items"][0]
    assert row["status"] == "partial"
    assert row["remaining_quantity"] == 2
    assert row["remaining_amount"] == 20
    assert first["remaining_total"] == 20

    # The legacy/item-id path must take only what remains, not try to take all 3.
    final = save_participant_selection(
        db, session, joined["participant_id"], selected_item_ids=[line.id]
    )
    assert final["items"][0]["remaining_quantity"] == 0
    assert final["remaining_total"] == 0
    quantities = sorted(
        a.quantity for a in db.query(SplitBillItemAssignment).filter_by(session_id=session.id).all()
    )
    assert quantities == [1, 2]


def test_identical_item_rows_remain_independent(db):
    owner = user(db)
    session, rows = make_bill(
        db,
        owner,
        [("Espresso", 1, 12, 12), ("Espresso", 1, 12, 12)],
    )
    guest = add_active_participant(db, "bob")
    joined = join_split_bill_session_as_user(db, session, guest)
    owner_participant = get_owner_participant(db, session)

    save_participant_selection(db, session, owner_participant.id, selected_item_ids=[rows[0].id])
    summary = save_participant_selection(db, session, joined["participant_id"], selected_item_ids=[rows[1].id])

    assert summary["remaining_total"] == 0
    assert [row["status"] for row in summary["items"]] == ["assigned", "assigned"]
    assert {a.receipt_item_id for a in db.query(SplitBillItemAssignment).all()} == {rows[0].id, rows[1].id}


def test_percentage_tip_is_based_on_each_persons_split(db):
    owner = user(db)
    session, rows = make_bill(db, owner, [("Main", 1, 80, 80), ("Dessert", 1, 20, 20)])
    guest = add_active_participant(db, "cara")
    joined = join_split_bill_session_as_user(db, session, guest)
    owner_participant = get_owner_participant(db, session)

    save_participant_selection(db, session, owner_participant.id, selected_item_ids=[rows[0].id])
    save_participant_selection(db, session, joined["participant_id"], selected_item_ids=[rows[1].id])
    summary = update_session_tip(db, session, owner.id, "percent", 10)
    by_id = {p["participant_id"]: p for p in summary["participants"]}

    assert by_id[owner_participant.id]["item_total"] == 80
    assert by_id[owner_participant.id]["tip_share"] == 8
    assert by_id[owner_participant.id]["total"] == 88
    assert by_id[joined["participant_id"]]["item_total"] == 20
    assert by_id[joined["participant_id"]]["tip_share"] == 2
    assert by_id[joined["participant_id"]]["total"] == 22
    assert summary["tip_total"] == 10
    assert summary["grand_total"] == 110


def test_history_tracks_role_and_owner_only_reopen_resets_payment(db):
    owner = user(db)
    session, (line,) = make_bill(db, owner, [("Dinner", 2, 25, 50)])
    guest = add_active_participant(db, "dana")
    joined = join_split_bill_session_as_user(db, session, guest)
    owner_participant = get_owner_participant(db, session)

    save_participant_selection(db, session, owner_participant.id, selected_quantities={line.id: 1})
    save_participant_selection(db, session, joined["participant_id"], selected_quantities={line.id: 1})

    owner_history = list_split_bill_sessions_for_user(db, owner.id)
    guest_history = list_split_bill_sessions_for_user(db, guest.id)
    assert owner_history[0]["role"] == "owner" and owner_history[0]["status"] == "open"
    assert guest_history[0]["role"] == "participant" and guest_history[0]["status"] == "open"

    close_split_bill_session(db, session, owner.id)
    record_participant_payment_status(db, session, joined["participant_id"], "bank_transfer", paid=True)
    assert list_split_bill_sessions_for_user(db, guest.id)[0]["status"] == "settled"

    with pytest.raises(ValueError, match="Only the bill owner"):
        reopen_split_bill_session(db, session, guest.id)

    reopened = reopen_split_bill_session(db, session, owner.id)
    assert reopened["status"] == "open"
    assert reopened["remaining_total"] == 0  # allocations are preserved
    participants = db.query(SplitBillParticipant).filter_by(session_id=session.id).all()
    assert all(p.payment_status == "unpaid" and p.payment_method is None and p.paid_at is None for p in participants)
    assert list_split_bill_sessions_for_user(db, owner.id)[0]["status"] == "open"


def test_username_is_derived_from_first_name_and_surname(db, delivery):
    assert username_base_from_name("Ștefan Țurcanu") == "stefan.turcanu"

    first = otp.start_registration(
        db,
        phone_number="+40730000001",
        display_name="Ana Popescu",
        email="ana1@example.com",
        accepted_terms=True,
        accepted_privacy=True,
        password="testing-password",
        username=None,
    )["user"]
    second = otp.start_registration(
        db,
        phone_number="+40730000002",
        display_name="Ana Popescu",
        email="ana2@example.com",
        accepted_terms=True,
        accepted_privacy=True,
        password="testing-password",
        username=None,
    )["user"]

    assert first.username == "ana.popescu"
    assert second.username == "ana.popescu.2"
