"""Regression coverage for Pruvs v6.6 live split allocation behavior."""

from test_device_otp import db, user
from test_split_bill_v6_5 import make_bill, add_active_participant
from app.services.split_bill_session_service import (
    close_split_bill_session,
    get_owner_participant,
    join_split_bill_session_as_user,
    reopen_split_bill_session,
    save_participant_selection,
)


def test_summary_keeps_every_participant_quantity_after_reopen(db):
    owner = user(db)
    session, (line,) = make_bill(db, owner, [("Tap water", 4, 5, 20)], expected=3)
    alice = add_active_participant(db, "livealice")
    bob = add_active_participant(db, "livebob")
    alice_join = join_split_bill_session_as_user(db, session, alice)
    bob_join = join_split_bill_session_as_user(db, session, bob)
    owner_participant = get_owner_participant(db, session)

    save_participant_selection(db, session, owner_participant.id, selected_quantities={line.id: 1})
    save_participant_selection(db, session, alice_join["participant_id"], selected_quantities={line.id: 1})
    summary = save_participant_selection(db, session, bob_join["participant_id"], selected_quantities={line.id: 2})

    item = summary["items"][0]
    assert item["status"] == "assigned"
    assert item["remaining_quantity"] == 0
    assert [(a["assigned_to"], a["quantity"]) for a in item["assignments"]] == [
        (owner.name, 1), (alice.name, 1), (bob.name, 2)
    ]

    close_split_bill_session(db, session, owner.id)
    reopened = reopen_split_bill_session(db, session, owner.id)
    item = reopened["items"][0]
    assert item["status"] == "assigned"
    assert [(a["assigned_to"], a["quantity"]) for a in item["assignments"]] == [
        (owner.name, 1), (alice.name, 1), (bob.name, 2)
    ]


def test_last_available_units_cannot_be_overclaimed_sequentially(db):
    owner = user(db)
    session, (line,) = make_bill(db, owner, [("Cola", 2, 10, 20)], expected=3)
    alice = add_active_participant(db, "racealice")
    bob = add_active_participant(db, "racebob")
    alice_join = join_split_bill_session_as_user(db, session, alice)
    bob_join = join_split_bill_session_as_user(db, session, bob)

    save_participant_selection(db, session, alice_join["participant_id"], selected_quantities={line.id: 2})
    try:
        save_participant_selection(db, session, bob_join["participant_id"], selected_quantities={line.id: 1})
    except ValueError as error:
        assert "remain available" in str(error)
    else:
        raise AssertionError("A second participant must not claim units already allocated to someone else")
