"""Selection confirmation contract: account-owned, additive and separate from payments."""
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def test_selection_confirmed_schema_is_additive_and_idempotent():
    import app.db.database as database
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE split_bill_participants (id INTEGER PRIMARY KEY)'))
    with patch.object(database, 'engine', engine):
        database.ensure_compatibility_schema()
        database.ensure_compatibility_schema()
    fields = {col['name'] for col in inspect(engine).get_columns('split_bill_participants')}
    assert 'selection_confirmed_at' in fields
    engine.dispose()


def test_server_action_does_not_trust_client_participant_or_mark_paid():
    routes = (ROOT/'app/react_app/api.py').read_text(encoding='utf-8')
    service = (ROOT/'app/react_app/bill_service.py').read_text(encoding='utf-8')
    action = routes.split("def complete_bill_selection(", 1)[1].split("\n\n@router.", 1)[0]
    assert "member(db,token,uid,lock=True)" in action
    assert "bills.confirm_participant_selection(db,s,p.id,uid)" in action
    assert "body.get(" not in action
    confirm = service.split("def confirm_participant_selection(", 1)[1].split("\n\ndef close_split_bill_session(",1)[0]
    assert 'session.status != "open"' in confirm
    assert 'user_id=actor_user_id' in confirm
    assert 'status="joined"' in confirm
    assert 'Select at least one item' in confirm
    assert "participant.selection_confirmed_at = datetime.utcnow()" in confirm
    assert "enqueue_selection_confirmed(db, session, participant)" in confirm
    assert "participant.payment_status =" not in confirm
    assert "db.commit()" in confirm


def test_selection_edits_invalidate_confirmation_and_owner_allocation_resets_all():
    service = (ROOT/'app/react_app/bill_service.py').read_text(encoding='utf-8')
    edits = service.split("def save_participant_selection(",1)[1].split("\n\ndef confirm_participant_selection(",1)[0]
    assert "participant.selection_confirmed_at = None" in edits
    model = (ROOT/'app/models/split_bill_participant.py').read_text(encoding='utf-8')
    assert "selection_confirmed_at = Column(DateTime, nullable=True)" in model
    allocation = (ROOT/'app/react_app/split_v7140.py').read_text(encoding='utf-8')
    assert "SplitBillParticipant.selection_confirmed_at: None" in allocation
    assert "bump(state,db)" in allocation
    reopen = service.split("def reopen_split_bill_session(",1)[1].split("\n\ndef list_split_bill_sessions_for_user(",1)[0]
    assert "participant.selection_confirmed_at = None" in reopen


def test_selection_notifications_owner_only_and_openable():
    events = (ROOT/'app/react_app/events.py').read_text(encoding='utf-8')
    segment = events.split("def enqueue_selection_confirmed(",1)[1].split("\n\ndef enqueue_transition(",1)[0]
    assert "session.owner_user_id" in segment
    assert "enqueue(db, owner.id, 'selection_confirmed'" in segment
    assert "f'/bill/{session.token}'" in segment
    assert "?view=summary" not in segment
    inbox = (ROOT/'app/react_app/inbox.py').read_text(encoding='utf-8')
    assert inbox.count("'selection_confirmed'") >= 2
    worker = (ROOT/'app/react_app/push_worker.py').read_text(encoding='utf-8')
    assert "'selection_confirmed'" in worker


def test_bill_next_reaches_existing_summary_without_creating_a_payment():
    bill = (ROOT/'frontend/src/Bill.jsx').read_text(encoding='utf-8')
    css = (ROOT/'frontend/src/floating-bill-workspace.css').read_text(encoding='utf-8')
    assert "Confirm selection & Next" in bill
    assert "selection/complete" in bill
    assert "chooseSection('summary')" in bill
    assert "selection_confirmed_at" in bill
    assert "Participant selection confirmations" in bill
    assert 'id="core-bill-summary"' in bill
    assert 'id="core-bill-settle"' in bill
    assert 'pruvs-next-summary' in css
