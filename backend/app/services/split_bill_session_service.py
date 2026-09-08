import os
import re
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment


def get_owner_participant(
    db: Session,
    session: SplitBillSession
) -> SplitBillParticipant | None:
    return (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.role == "owner"
        )
        .first()
    )


def get_participant_by_session_and_phone(
    db: Session,
    session: SplitBillSession,
    phone_number: str
) -> SplitBillParticipant | None:
    normalized_phone = normalize_phone_number(phone_number)

    return (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.phone_number == normalized_phone
        )
        .first()
    )


def get_public_base_url() -> str:
    return os.getenv(
        "PUBLIC_BASE_URL",
        "http://127.0.0.1:8000"
    ).rstrip("/")


def normalize_phone_number(phone_number: str) -> str:
    raw = (phone_number or "").strip()
    digits = re.sub(r"\D", "", raw)

    if not digits:
        raise ValueError("Phone number is required.")

    if raw.startswith("+"):
        return "+" + digits

    if digits.startswith("00"):
        return "+" + digits[2:]

    if digits.startswith("0") and len(digits) == 10:
        return "+40" + digits[1:]

    return "+" + digits


def generate_session_token() -> str:
    return "sb_" + secrets.token_urlsafe(16)


def generate_participant_token() -> str:
    return "pt_" + secrets.token_urlsafe(16)


def build_share_url(token: str) -> str:
    return f"{get_public_base_url()}/s/{token}"


def build_qr_url(token: str) -> str:
    return f"{get_public_base_url()}/split-bill/sessions/{token}/qr"


def build_widget_url(token: str, participant_id: int | None = None) -> str:
    base = f"{get_public_base_url()}/split-bill/sessions/{token}/widget-ui"

    if participant_id:
        return f"{base}?participant_id={participant_id}"

    return base


# Kept for compatibility with previous widget version.
def build_participant_url(session_token: str, participant_token: str) -> str:
    return (
        f"{get_public_base_url()}/split-bill/sessions/"
        f"{session_token}/p/{participant_token}/widget-ui"
    )


def get_user_by_phone_number(
    db: Session,
    phone_number: str
) -> User | None:
    normalized_phone = normalize_phone_number(phone_number)

    return (
        db.query(User)
        .filter(User.phone_number == normalized_phone)
        .first()
    )


def create_pending_user_if_missing(
    db: Session,
    phone_number: str,
    display_name: str | None = None
) -> User:
    normalized_phone = normalize_phone_number(phone_number)

    existing_user = (
        db.query(User)
        .filter(User.phone_number == normalized_phone)
        .first()
    )

    if existing_user:
        return existing_user

    user = User(
        phone_number=normalized_phone,
        name=display_name,
        status="pending_join",
        accepted_terms=False
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def get_joined_participants(
    db: Session,
    session: SplitBillSession
) -> list[SplitBillParticipant]:
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.session_id == session.id)
        .order_by(SplitBillParticipant.created_at.asc())
        .all()
    )


def get_joined_participants_count(
    db: Session,
    session: SplitBillSession
) -> int:
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.session_id == session.id)
        .count()
    )


def ensure_owner_participant(
    db: Session,
    session: SplitBillSession,
    owner: User
) -> SplitBillParticipant:
    existing = (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.user_id == owner.id
        )
        .first()
    )

    if existing:
        existing.role = "owner"
        existing.status = "joined"
        db.commit()
        db.refresh(existing)
        return existing

    participant = SplitBillParticipant(
        session_id=session.id,
        user_id=owner.id,
        display_name=owner.name or owner.phone_number or "Owner",
        phone_number=owner.phone_number,
        participant_token=generate_participant_token(),
        role="owner",
        status="joined"
    )

    db.add(participant)
    db.commit()
    db.refresh(participant)

    return participant


def create_split_bill_session(
    db: Session,
    case_id: int,
    owner_user_id: int,
    expected_participants_count: int
) -> SplitBillSession:
    if expected_participants_count < 1:
        raise ValueError("Expected participants count must be at least 1.")

    owner = (
        db.query(User)
        .filter(User.id == owner_user_id)
        .first()
    )

    if not owner:
        raise ValueError("Owner user not found.")

    if owner.status != "active":
        raise ValueError("Owner user must be active before creating a split bill session.")

    items = (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == case_id)
        .all()
    )

    if not items:
        raise ValueError("No receipt items found for this case.")

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
        ensure_owner_participant(
            db=db,
            session=existing,
            owner=owner
        )

        joined_count = get_joined_participants_count(
            db=db,
            session=existing
        )

        if expected_participants_count < joined_count:
            raise ValueError(
                f"This session already has {joined_count} joined participants. "
                f"Expected participants count cannot be lower than current joined count."
            )

        existing.owner_user_id = owner_user_id
        existing.expected_participants_count = expected_participants_count

        db.commit()
        db.refresh(existing)

        return existing

    currency = items[0].currency if items else "RON"

    session = SplitBillSession(
        case_id=case_id,
        owner_user_id=owner_user_id,
        token=generate_session_token(),
        status="open",
        currency=currency,
        expected_participants_count=expected_participants_count
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    ensure_owner_participant(
        db=db,
        session=session,
        owner=owner
    )

    return session


def get_split_bill_session_by_token(
    db: Session,
    token: str
) -> SplitBillSession | None:
    return (
        db.query(SplitBillSession)
        .filter(SplitBillSession.token == token)
        .first()
    )


def get_split_bill_participant_by_id(
    db: Session,
    participant_id: int
) -> SplitBillParticipant | None:
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.id == participant_id)
        .first()
    )


def get_split_bill_participant_by_token(
    db: Session,
    participant_token: str
) -> SplitBillParticipant | None:
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.participant_token == participant_token)
        .first()
    )


def get_participant_by_session_and_user(
    db: Session,
    session: SplitBillSession,
    user: User
) -> SplitBillParticipant | None:
    return (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.user_id == user.id
        )
        .first()
    )


# Kept for compatibility with previous open-name widget.
def create_split_bill_participant(
    db: Session,
    session: SplitBillSession,
    display_name: str
) -> SplitBillParticipant:
    participant = SplitBillParticipant(
        session_id=session.id,
        user_id=None,
        display_name=display_name.strip(),
        phone_number=None,
        participant_token=generate_participant_token(),
        role="participant",
        status="joined"
    )

    db.add(participant)
    db.commit()
    db.refresh(participant)

    return participant


def join_split_bill_session(
    db: Session,
    session: SplitBillSession,
    phone_number: str,
    display_name: str | None = None
) -> dict:
    if session.status != "open":
        return {
            "status": "session_closed",
            "message": "This split bill session is no longer open.",
            "user_status": None,
            "participant_id": None,
            "participant_token": None,
            "display_name": None,
            "widget_url": None
        }

    normalized_phone = normalize_phone_number(phone_number)

    user = (
        db.query(User)
        .filter(User.phone_number == normalized_phone)
        .first()
    )

    if not user:
        user = create_pending_user_if_missing(
            db=db,
            phone_number=normalized_phone,
            display_name=display_name
        )

        return {
            "status": "requires_onboarding",
            "message": (
                "This phone number is not active in Pruvio yet. "
                "Please create or activate your Pruvio account before joining this bill."
            ),
            "user_status": user.status,
            "participant_id": None,
            "participant_token": None,
            "display_name": display_name,
            "widget_url": None
        }

    if user.status != "active":
        return {
            "status": "requires_onboarding",
            "message": (
                "Your Pruvio account is not active yet. "
                "Please complete onboarding before joining this bill."
            ),
            "user_status": user.status,
            "participant_id": None,
            "participant_token": None,
            "display_name": user.name or display_name,
            "widget_url": None
        }

    existing_participant = get_participant_by_session_and_user(
        db=db,
        session=session,
        user=user
    )

    if not existing_participant:
        existing_participant = get_participant_by_session_and_phone(
            db=db,
            session=session,
            phone_number=normalized_phone
        )

    if existing_participant:
        if existing_participant.user_id is None:
            existing_participant.user_id = user.id

        if not existing_participant.phone_number:
            existing_participant.phone_number = normalized_phone

        if display_name and existing_participant.display_name != display_name:
            existing_participant.display_name = display_name

        existing_participant.status = "joined"

        db.commit()
        db.refresh(existing_participant)

        return {
            "status": "already_joined",
            "message": "You already joined this split bill session.",
            "user_status": user.status,
            "participant_id": existing_participant.id,
            "participant_token": existing_participant.participant_token,
            "display_name": existing_participant.display_name,
            "widget_url": build_widget_url(
                token=session.token,
                participant_id=existing_participant.id
            )
        }

    joined_count = get_joined_participants_count(
        db=db,
        session=session
    )

    if joined_count >= session.expected_participants_count:
        return {
            "status": "session_full",
            "message": "All expected participants have already joined this bill.",
            "user_status": user.status,
            "participant_id": None,
            "participant_token": None,
            "display_name": user.name or display_name,
            "widget_url": None
        }

    participant = SplitBillParticipant(
        session_id=session.id,
        user_id=user.id,
        display_name=display_name or user.name or normalized_phone,
        phone_number=normalized_phone,
        participant_token=generate_participant_token(),
        role="participant",
        status="joined"
    )

    db.add(participant)
    db.commit()
    db.refresh(participant)

    return {
        "status": "joined",
        "message": "You joined the split bill session.",
        "user_status": user.status,
        "participant_id": participant.id,
        "participant_token": participant.participant_token,
        "display_name": participant.display_name,
        "widget_url": build_widget_url(
            token=session.token,
            participant_id=participant.id
        )
    }


def get_session_items(
    db: Session,
    session: SplitBillSession
) -> list[ReceiptItem]:
    return (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == session.case_id)
        .order_by(ReceiptItem.id.asc())
        .all()
    )


def get_session_assignments(
    db: Session,
    session: SplitBillSession
) -> list[SplitBillItemAssignment]:
    return (
        db.query(SplitBillItemAssignment)
        .filter(SplitBillItemAssignment.session_id == session.id)
        .all()
    )


def get_close_state(
    db: Session,
    session: SplitBillSession,
    remaining_total: float | None = None
) -> dict:
    joined_count = get_joined_participants_count(
        db=db,
        session=session
    )

    missing_count = max(
        session.expected_participants_count - joined_count,
        0
    )

    if remaining_total is None:
        summary = get_split_bill_session_summary(
            db=db,
            session=session
        )
        remaining_total = summary["remaining_total"]

    if session.status != "open":
        return {
            "can_close": False,
            "close_block_reason": "Session is not open.",
            "joined_participants_count": joined_count,
            "missing_participants_count": missing_count
        }

    if missing_count > 0:
        return {
            "can_close": False,
            "close_block_reason": (
                f"Waiting for {missing_count} more participant"
                f"{'s' if missing_count != 1 else ''} to join."
            ),
            "joined_participants_count": joined_count,
            "missing_participants_count": missing_count
        }

    if round(remaining_total, 2) > 0:
        return {
            "can_close": False,
            "close_block_reason": (
                f"Some items are still not assigned. "
                f"Remaining total: {remaining_total:.2f} {session.currency}."
            ),
            "joined_participants_count": joined_count,
            "missing_participants_count": missing_count
        }

    return {
        "can_close": True,
        "close_block_reason": None,
        "joined_participants_count": joined_count,
        "missing_participants_count": missing_count
    }


def get_split_bill_session_summary(
    db: Session,
    session: SplitBillSession
) -> dict:
    items = get_session_items(
        db=db,
        session=session
    )

    assignments = get_session_assignments(
        db=db,
        session=session
    )

    participants = get_joined_participants(
        db=db,
        session=session
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
                "status": "assigned" if assignment else "available",
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
                "user_id": participant.user_id,
                "display_name": participant.display_name,
                "phone_number": participant.phone_number,
                "role": participant.role,
                "status": participant.status,
                "items_count": len(participant_assignments),
                "total": participant_total,
                "currency": session.currency
            }
        )

    close_state = get_close_state(
        db=db,
        session=session,
        remaining_total=remaining_total
    )

    return {
        "session_id": session.id,
        "case_id": session.case_id,
        "owner_user_id": session.owner_user_id,
        "token": session.token,
        "status": session.status,
        "expected_participants_count": session.expected_participants_count,
        "joined_participants_count": close_state["joined_participants_count"],
        "missing_participants_count": close_state["missing_participants_count"],
        "bill_total": bill_total,
        "assigned_total": assigned_total,
        "remaining_total": remaining_total,
        "currency": session.currency,
        "can_close": close_state["can_close"],
        "close_block_reason": close_state["close_block_reason"],
        "participants": participant_rows,
        "items": item_rows,
        "share_url": build_share_url(session.token),
        "qr_url": build_qr_url(session.token)
    }


def save_participant_selection(
    db: Session,
    session: SplitBillSession,
    participant_id: int,
    selected_item_ids: list[int]
) -> dict:
    if session.status != "open":
        raise ValueError("This split bill session is closed.")

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

    valid_item_ids = {
        item.id
        for item in valid_items
    }

    selected_set = set(selected_item_ids)
    invalid_ids = selected_set - valid_item_ids

    if invalid_ids:
        raise ValueError(
            f"Invalid item IDs for this session: {sorted(invalid_ids)}"
        )

    existing_assignments = get_session_assignments(
        db=db,
        session=session
    )

    already_taken_by_others = {
        assignment.receipt_item_id
        for assignment in existing_assignments
        if assignment.participant_id != participant_id
    }

    conflicts = selected_set.intersection(already_taken_by_others)

    if conflicts:
        raise ValueError(
            f"Some items are already selected by another participant: {sorted(conflicts)}"
        )

    db.query(SplitBillItemAssignment).filter(
        SplitBillItemAssignment.session_id == session.id,
        SplitBillItemAssignment.participant_id == participant_id
    ).delete()

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


def close_split_bill_session(
    db: Session,
    session: SplitBillSession,
    owner_user_id: int
) -> dict:
    if session.owner_user_id != owner_user_id:
        raise ValueError("Only the bill owner can close this session.")

    summary = get_split_bill_session_summary(
        db=db,
        session=session
    )

    if not summary["can_close"]:
        raise ValueError(summary["close_block_reason"])

    session.status = "closed"
    session.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(session)

    return {
        "session_id": session.id,
        "status": session.status,
        "closed_at": session.closed_at,
        "message": "Split bill session was closed successfully."
    }