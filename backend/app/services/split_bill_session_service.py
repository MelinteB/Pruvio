import os
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment


def get_public_base_url() -> str:
    return os.getenv(
        "PUBLIC_BASE_URL",
        "http://127.0.0.1:8000"
    ).rstrip("/")


def generate_session_token() -> str:
    return "sb_" + secrets.token_urlsafe(16)


def generate_participant_token() -> str:
    return "pt_" + secrets.token_urlsafe(16)


def build_share_url(token: str) -> str:
    return f"{get_public_base_url()}/split-bill/sessions/{token}/widget-ui"


def build_qr_url(token: str) -> str:
    return f"{get_public_base_url()}/split-bill/sessions/{token}/qr"


def create_split_bill_session(
    db: Session,
    case_id: int
):
    existing = (
        db.query(SplitBillSession)
        .filter(
            SplitBillSession.case_id == case_id,
            SplitBillSession.status == "open"
        )
        .order_by(SplitBillSession.created_at.desc())
        .first()
    )

    if existing:
        return existing

    items = (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == case_id)
        .all()
    )

    currency = items[0].currency if items else "RON"

    session = SplitBillSession(
        case_id=case_id,
        token=generate_session_token(),
        status="open",
        currency=currency
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_split_bill_session_by_token(
    db: Session,
    token: str
):
    return (
        db.query(SplitBillSession)
        .filter(SplitBillSession.token == token)
        .first()
    )


def create_split_bill_participant(
    db: Session,
    session: SplitBillSession,
    display_name: str
):
    participant = SplitBillParticipant(
        session_id=session.id,
        display_name=display_name.strip(),
        participant_token=generate_participant_token()
    )

    db.add(participant)
    db.commit()
    db.refresh(participant)

    return participant


def get_split_bill_participant_by_id(
    db: Session,
    participant_id: int
):
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.id == participant_id)
        .first()
    )


def get_session_items(
    db: Session,
    session: SplitBillSession
):
    return (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == session.case_id)
        .order_by(ReceiptItem.id.asc())
        .all()
    )


def get_session_assignments(
    db: Session,
    session: SplitBillSession
):
    return (
        db.query(SplitBillItemAssignment)
        .filter(SplitBillItemAssignment.session_id == session.id)
        .all()
    )


def save_participant_selection(
    db: Session,
    session: SplitBillSession,
    participant_id: int,
    selected_item_ids: list[int]
):
    participant = get_split_bill_participant_by_id(
        db=db,
        participant_id=participant_id
    )

    if not participant or participant.session_id != session.id:
        raise ValueError("Participant does not belong to this split bill session.")

    valid_items = get_session_items(
        db=db,
        session=session
    )

    valid_item_ids = {item.id for item in valid_items}
    selected_set = set(selected_item_ids)

    invalid_ids = selected_set - valid_item_ids

    if invalid_ids:
        raise ValueError(f"Invalid item IDs for this session: {sorted(invalid_ids)}")

    # Remove previous assignments made by this participant.
    db.query(SplitBillItemAssignment).filter(
        SplitBillItemAssignment.session_id == session.id,
        SplitBillItemAssignment.participant_id == participant_id
    ).delete()

    # Check assignments from other participants.
    existing_assignments = (
        db.query(SplitBillItemAssignment)
        .filter(SplitBillItemAssignment.session_id == session.id)
        .all()
    )

    already_taken = {
        assignment.receipt_item_id
        for assignment in existing_assignments
        if assignment.participant_id != participant_id
    }

    conflicts = selected_set.intersection(already_taken)

    if conflicts:
        raise ValueError(
            f"Some items are already selected by another participant: {sorted(conflicts)}"
        )

    item_by_id = {
        item.id: item
        for item in valid_items
    }

    for item_id in selected_set:
        item = item_by_id[item_id]

        assignment = SplitBillItemAssignment(
            session_id=session.id,
            participant_id=participant_id,
            receipt_item_id=item.id,
            amount=item.total_price
        )

        db.add(assignment)

    db.commit()

    return get_split_bill_session_summary(
        db=db,
        session=session
    )


def get_split_bill_session_summary(
    db: Session,
    session: SplitBillSession
):
    items = get_session_items(
        db=db,
        session=session
    )

    assignments = get_session_assignments(
        db=db,
        session=session
    )

    participants = (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.session_id == session.id)
        .order_by(SplitBillParticipant.created_at.asc())
        .all()
    )

    participant_by_id = {
        participant.id: participant
        for participant in participants
    }

    assignment_by_item_id = {
        assignment.receipt_item_id: assignment
        for assignment in assignments
    }

    bill_total = round(
        sum(item.total_price for item in items),
        2
    )

    assigned_total = round(
        sum(assignment.amount for assignment in assignments),
        2
    )

    remaining_total = round(
        bill_total - assigned_total,
        2
    )

    item_rows = []

    for index, item in enumerate(items, start=1):
        assignment = assignment_by_item_id.get(item.id)
        participant = None

        if assignment:
            participant = participant_by_id.get(assignment.participant_id)

        item_rows.append(
            {
                "position": index,
                "item_id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "currency": item.currency,
                "status": "assigned" if assignment else "remaining",
                "assigned_to": participant.display_name if participant else None,
                "participant_id": participant.id if participant else None
            }
        )

    participant_rows = []

    for participant in participants:
        participant_assignments = [
            assignment
            for assignment in assignments
            if assignment.participant_id == participant.id
        ]

        participant_total = round(
            sum(assignment.amount for assignment in participant_assignments),
            2
        )

        participant_rows.append(
            {
                "participant_id": participant.id,
                "display_name": participant.display_name,
                "items_count": len(participant_assignments),
                "total": participant_total,
                "currency": session.currency
            }
        )

    return {
        "session_id": session.id,
        "case_id": session.case_id,
        "token": session.token,
        "status": session.status,
        "bill_total": bill_total,
        "assigned_total": assigned_total,
        "remaining_total": remaining_total,
        "currency": session.currency,
        "participants": participant_rows,
        "items": item_rows,
        "share_url": build_share_url(session.token),
        "qr_url": build_qr_url(session.token)
    }