import os
import re
import secrets
from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.receipt_item import ReceiptItem
from app.models.split_bill_session import SplitBillSession
from app.models.split_bill_participant import SplitBillParticipant
from app.models.split_bill_item_assignment import SplitBillItemAssignment
from app.services.receipt_translation_service import translate_receipt_item_names


MONEY_TOLERANCE = 0.05
QUANTITY_TOLERANCE = 1e-6


def get_owner_participant(db: Session, session: SplitBillSession) -> SplitBillParticipant | None:
    return (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.role == "owner",
        )
        .first()
    )


def get_participant_by_session_and_phone(
    db: Session,
    session: SplitBillSession,
    phone_number: str,
) -> SplitBillParticipant | None:
    normalized_phone = normalize_phone_number(phone_number)
    return (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.phone_number == normalized_phone,
        )
        .first()
    )


def get_public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


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


def build_participant_url(session_token: str, participant_token: str) -> str:
    return (
        f"{get_public_base_url()}/split-bill/sessions/"
        f"{session_token}/p/{participant_token}/widget-ui"
    )


def get_user_by_phone_number(db: Session, phone_number: str) -> User | None:
    normalized_phone = normalize_phone_number(phone_number)
    return db.query(User).filter(User.phone_number == normalized_phone).first()


def create_pending_user_if_missing(
    db: Session,
    phone_number: str,
    display_name: str | None = None,
) -> User:
    normalized_phone = normalize_phone_number(phone_number)
    existing_user = db.query(User).filter(User.phone_number == normalized_phone).first()
    if existing_user:
        return existing_user

    user = User(
        phone_number=normalized_phone,
        name=display_name,
        status="pending_join",
        accepted_terms=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_joined_participants(db: Session, session: SplitBillSession) -> list[SplitBillParticipant]:
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.session_id == session.id)
        .order_by(SplitBillParticipant.created_at.asc())
        .all()
    )


def get_joined_participants_count(db: Session, session: SplitBillSession) -> int:
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.session_id == session.id)
        .count()
    )


def ensure_owner_participant(
    db: Session,
    session: SplitBillSession,
    owner: User,
) -> SplitBillParticipant:
    existing = (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.user_id == owner.id,
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
        display_name=owner.name or "Owner",
        phone_number=owner.phone_number,
        participant_token=generate_participant_token(),
        role="owner",
        status="joined",
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


def create_split_bill_session(
    db: Session,
    case_id: int,
    owner_user_id: int,
    expected_participants_count: int,
) -> SplitBillSession:
    if expected_participants_count < 1:
        raise ValueError("Expected participants count must be at least 1.")
    if expected_participants_count > 20:
        raise ValueError("Expected participants count cannot be greater than 20.")

    owner = db.query(User).filter(User.id == owner_user_id).first()
    if not owner:
        raise ValueError("Owner user not found.")
    if owner.status != "active":
        raise ValueError("Owner user must be active before creating a split bill session.")

    items = db.query(ReceiptItem).filter(ReceiptItem.case_id == case_id).all()
    if not items:
        raise ValueError("No receipt items found for this case.")

    existing = (
        db.query(SplitBillSession)
        .filter(
            SplitBillSession.case_id == case_id,
            SplitBillSession.status == "open",
        )
        .order_by(SplitBillSession.created_at.desc())
        .first()
    )
    if existing:
        ensure_owner_participant(db, existing, owner)
        joined_count = get_joined_participants_count(db, existing)
        if expected_participants_count < joined_count:
            raise ValueError(
                f"This session already has {joined_count} joined participants. "
                "Expected participants count cannot be lower than current joined count."
            )
        existing.owner_user_id = owner_user_id
        existing.expected_participants_count = expected_participants_count
        db.commit()
        db.refresh(existing)
        return existing

    currency = items[0].currency or "—"
    session = SplitBillSession(
        case_id=case_id,
        owner_user_id=owner_user_id,
        token=generate_session_token(),
        status="open",
        currency=currency,
        expected_participants_count=expected_participants_count,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    ensure_owner_participant(db, session, owner)
    return session


def get_split_bill_session_by_token(db: Session, token: str) -> SplitBillSession | None:
    return db.query(SplitBillSession).filter(SplitBillSession.token == token).first()


def get_split_bill_participant_by_id(db: Session, participant_id: int) -> SplitBillParticipant | None:
    return db.query(SplitBillParticipant).filter(SplitBillParticipant.id == participant_id).first()


def get_split_bill_participant_by_token(
    db: Session,
    participant_token: str,
) -> SplitBillParticipant | None:
    return (
        db.query(SplitBillParticipant)
        .filter(SplitBillParticipant.participant_token == participant_token)
        .first()
    )


def get_participant_by_session_and_user(
    db: Session,
    session: SplitBillSession,
    user: User,
) -> SplitBillParticipant | None:
    return (
        db.query(SplitBillParticipant)
        .filter(
            SplitBillParticipant.session_id == session.id,
            SplitBillParticipant.user_id == user.id,
        )
        .first()
    )


def create_split_bill_participant(
    db: Session,
    session: SplitBillSession,
    display_name: str,
) -> SplitBillParticipant:
    name = (display_name or "").strip()
    if not name:
        raise ValueError("Display name is required.")

    participant = SplitBillParticipant(
        session_id=session.id,
        user_id=None,
        display_name=name,
        phone_number=None,
        participant_token=generate_participant_token(),
        role="participant",
        status="joined",
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


def join_split_bill_session(
    db: Session,
    session: SplitBillSession,
    phone_number: str | None = None,
    display_name: str | None = None,
) -> dict:
    if session.status != "open":
        return {
            "status": "session_closed",
            "message": "This split bill session is no longer open.",
            "user_status": None,
            "participant_id": None,
            "participant_token": None,
            "display_name": None,
            "widget_url": None,
        }

    joined_count = get_joined_participants_count(db, session)

    # Standalone app path: joining only requires a display name.
    if not phone_number:
        name = (display_name or "").strip()
        if not name:
            raise ValueError("Please enter your name.")
        if joined_count >= session.expected_participants_count:
            return {
                "status": "session_full",
                "message": "All expected participants have already joined this bill.",
                "user_status": None,
                "participant_id": None,
                "participant_token": None,
                "display_name": name,
                "widget_url": None,
            }

        participant = create_split_bill_participant(db, session, name)
        return {
            "status": "joined",
            "message": "You joined the split bill session.",
            "user_status": None,
            "participant_id": participant.id,
            "participant_token": participant.participant_token,
            "display_name": participant.display_name,
            "widget_url": build_participant_url(session.token, participant.participant_token),
        }

    # Backward-compatible phone/account path.
    normalized_phone = normalize_phone_number(phone_number)
    user = db.query(User).filter(User.phone_number == normalized_phone).first()
    if not user:
        user = create_pending_user_if_missing(db, normalized_phone, display_name)
        return {
            "status": "requires_onboarding",
            "message": "This phone number is not active in Pruvio yet.",
            "user_status": user.status,
            "participant_id": None,
            "participant_token": None,
            "display_name": display_name,
            "widget_url": None,
        }
    if user.status != "active":
        return {
            "status": "requires_onboarding",
            "message": "Your Pruvio account is not active yet.",
            "user_status": user.status,
            "participant_id": None,
            "participant_token": None,
            "display_name": user.name or display_name,
            "widget_url": None,
        }

    existing = get_participant_by_session_and_user(db, session, user)
    if not existing:
        existing = get_participant_by_session_and_phone(db, session, normalized_phone)
    if existing:
        existing.user_id = existing.user_id or user.id
        existing.phone_number = existing.phone_number or normalized_phone
        if display_name:
            existing.display_name = display_name
        existing.status = "joined"
        db.commit()
        db.refresh(existing)
        return {
            "status": "already_joined",
            "message": "You already joined this split bill session.",
            "user_status": user.status,
            "participant_id": existing.id,
            "participant_token": existing.participant_token,
            "display_name": existing.display_name,
            "widget_url": build_participant_url(session.token, existing.participant_token),
        }

    if joined_count >= session.expected_participants_count:
        return {
            "status": "session_full",
            "message": "All expected participants have already joined this bill.",
            "user_status": user.status,
            "participant_id": None,
            "participant_token": None,
            "display_name": user.name or display_name,
            "widget_url": None,
        }

    participant = SplitBillParticipant(
        session_id=session.id,
        user_id=user.id,
        display_name=display_name or user.name or normalized_phone,
        phone_number=normalized_phone,
        participant_token=generate_participant_token(),
        role="participant",
        status="joined",
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
        "widget_url": build_participant_url(session.token, participant.participant_token),
    }


def get_session_items(db: Session, session: SplitBillSession) -> list[ReceiptItem]:
    return (
        db.query(ReceiptItem)
        .filter(ReceiptItem.case_id == session.case_id)
        .order_by(ReceiptItem.id.asc())
        .all()
    )


def get_session_assignments(
    db: Session,
    session: SplitBillSession,
) -> list[SplitBillItemAssignment]:
    return (
        db.query(SplitBillItemAssignment)
        .filter(SplitBillItemAssignment.session_id == session.id)
        .order_by(SplitBillItemAssignment.id.asc())
        .all()
    )


def _ensure_item_translations(db: Session, items: list[ReceiptItem]) -> None:
    if not items or all(item.source_language for item in items):
        return
    result = translate_receipt_item_names([item.name for item in items])
    if result.error or not result.source_language:
        if result.error:
            print(f"Receipt translation backfill skipped: {result.error}")
        return
    for item in items:
        if not item.source_language:
            item.source_language = result.source_language
        translated = result.translated_names.get(item.name)
        if translated:
            item.translated_name = translated
    db.commit()


def _item_quantity(item: ReceiptItem) -> float:
    quantity = float(item.quantity or 1)
    return quantity if quantity > 0 else 1.0


def _item_unit_price(item: ReceiptItem) -> float:
    if item.unit_price is not None:
        return float(item.unit_price)
    return float(item.total_price or 0) / _item_quantity(item)


def _assignment_quantity(assignment: SplitBillItemAssignment, item: ReceiptItem) -> float:
    if assignment.quantity is not None and float(assignment.quantity) > 0:
        return float(assignment.quantity)
    unit_price = _item_unit_price(item)
    if unit_price > 0:
        return max(0.0, float(assignment.amount or 0) / unit_price)
    return _item_quantity(item)


def _amount_for_quantity(item: ReceiptItem, quantity: float) -> float:
    total_quantity = _item_quantity(item)
    if abs(quantity - total_quantity) <= QUANTITY_TOLERANCE:
        return round(float(item.total_price or 0), 2)
    return round(_item_unit_price(item) * quantity, 2)


def get_close_state(
    db: Session,
    session: SplitBillSession,
    remaining_total: float | None = None,
) -> dict:
    joined_count = get_joined_participants_count(db, session)
    missing_count = max(session.expected_participants_count - joined_count, 0)

    if remaining_total is None:
        remaining_total = get_split_bill_session_summary(db, session)["remaining_total"]

    if session.status != "open":
        reason = "Session is not open."
    elif missing_count > 0:
        reason = f"Waiting for {missing_count} more participant{'s' if missing_count != 1 else ''} to join."
    elif remaining_total > MONEY_TOLERANCE:
        reason = f"Some items are still not assigned. Remaining total: {remaining_total:.2f} {session.currency}."
    else:
        reason = None

    return {
        "can_close": reason is None,
        "close_block_reason": reason,
        "joined_participants_count": joined_count,
        "missing_participants_count": missing_count,
    }


def get_split_bill_session_summary(db: Session, session: SplitBillSession) -> dict:
    items = get_session_items(db, session)
    _ensure_item_translations(db, items)
    assignments = get_session_assignments(db, session)
    participants = get_joined_participants(db, session)

    participant_by_id = {participant.id: participant for participant in participants}
    item_by_id = {item.id: item for item in items}
    assignments_by_item: dict[int, list[SplitBillItemAssignment]] = defaultdict(list)
    assignments_by_participant: dict[int, list[SplitBillItemAssignment]] = defaultdict(list)
    for assignment in assignments:
        assignments_by_item[assignment.receipt_item_id].append(assignment)
        assignments_by_participant[assignment.participant_id].append(assignment)

    bill_total = round(sum(float(item.total_price or 0) for item in items), 2)
    assigned_total = round(sum(float(assignment.amount or 0) for assignment in assignments), 2)
    remaining_total = round(max(0.0, bill_total - assigned_total), 2)

    item_rows = []
    for index, item in enumerate(items, start=1):
        item_assignments = assignments_by_item.get(item.id, [])
        total_quantity = _item_quantity(item)
        assignment_rows = []
        assigned_quantity = 0.0

        for assignment in item_assignments:
            participant = participant_by_id.get(assignment.participant_id)
            quantity = _assignment_quantity(assignment, item)
            assigned_quantity += quantity
            assignment_rows.append(
                {
                    "assignment_id": assignment.id,
                    "participant_id": assignment.participant_id,
                    "assigned_to": participant.display_name if participant else "Participant",
                    "quantity": round(quantity, 3),
                    "amount": round(float(assignment.amount or 0), 2),
                }
            )

        assigned_quantity = min(total_quantity, assigned_quantity)
        remaining_quantity = max(0.0, total_quantity - assigned_quantity)
        if assigned_quantity <= QUANTITY_TOLERANCE:
            status = "available"
        elif remaining_quantity <= QUANTITY_TOLERANCE:
            status = "assigned"
        else:
            status = "partial"

        # Compatibility fields refer to the sole assignment only. New UI uses assignments[].
        sole_assignment = assignment_rows[0] if len(assignment_rows) == 1 else None
        item_rows.append(
            {
                "position": index,
                "item_id": item.id,
                "name": item.name,
                "original_name": item.name,
                "translated_name": item.translated_name,
                "source_language": item.source_language,
                "quantity": total_quantity,
                "unit_price": _item_unit_price(item),
                "total_price": float(item.total_price or 0),
                "currency": item.currency or session.currency,
                "status": status,
                "assigned_quantity": round(assigned_quantity, 3),
                "remaining_quantity": round(remaining_quantity, 3),
                "assignments": assignment_rows,
                "assigned_to": sole_assignment["assigned_to"] if sole_assignment else None,
                "participant_id": sole_assignment["participant_id"] if sole_assignment else None,
            }
        )

    participant_rows = []
    for participant in participants:
        participant_assignments = assignments_by_participant.get(participant.id, [])
        participant_total = round(sum(float(a.amount or 0) for a in participant_assignments), 2)
        units_count = 0.0
        for assignment in participant_assignments:
            item = item_by_id.get(assignment.receipt_item_id)
            if item:
                units_count += _assignment_quantity(assignment, item)
        participant_rows.append(
            {
                "participant_id": participant.id,
                "user_id": participant.user_id,
                "display_name": participant.display_name,
                "phone_number": participant.phone_number,
                "role": participant.role,
                "status": participant.status,
                "items_count": len(participant_assignments),
                "units_count": round(units_count, 3),
                "total": participant_total,
                "currency": session.currency,
            }
        )

    close_state = get_close_state(db, session, remaining_total=remaining_total)
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
        "qr_url": build_qr_url(session.token),
    }


def save_participant_selection(
    db: Session,
    session: SplitBillSession,
    participant_id: int,
    selected_quantities: dict[int, float] | None = None,
    selected_item_ids: list[int] | None = None,
) -> dict:
    if session.status != "open":
        raise ValueError("This split bill session is closed.")

    participant = get_split_bill_participant_by_id(db, participant_id)
    if not participant or participant.session_id != session.id:
        raise ValueError("Participant does not belong to this split bill session.")

    valid_items = get_session_items(db, session)
    item_by_id = {item.id: item for item in valid_items}

    requested: dict[int, float] = {}
    for raw_id, raw_quantity in (selected_quantities or {}).items():
        item_id = int(raw_id)
        quantity = float(raw_quantity or 0)
        if quantity > QUANTITY_TOLERANCE:
            requested[item_id] = quantity

    # Old API compatibility: item id means the whole line quantity.
    for item_id in selected_item_ids or []:
        if item_id in item_by_id and item_id not in requested:
            requested[item_id] = _item_quantity(item_by_id[item_id])

    invalid_ids = set(requested) - set(item_by_id)
    if invalid_ids:
        raise ValueError(f"Invalid item IDs for this session: {sorted(invalid_ids)}")

    existing_assignments = get_session_assignments(db, session)
    other_quantity_by_item: dict[int, float] = defaultdict(float)
    for assignment in existing_assignments:
        if assignment.participant_id == participant_id:
            continue
        item = item_by_id.get(assignment.receipt_item_id)
        if item:
            other_quantity_by_item[item.id] += _assignment_quantity(assignment, item)

    for item_id, quantity in requested.items():
        item = item_by_id[item_id]
        if quantity < 0:
            raise ValueError("Selected quantity cannot be negative.")
        available = max(0.0, _item_quantity(item) - other_quantity_by_item[item_id])
        if quantity - available > QUANTITY_TOLERANCE:
            raise ValueError(
                f"Only {available:g} unit(s) of '{item.name}' remain available."
            )

    db.query(SplitBillItemAssignment).filter(
        SplitBillItemAssignment.session_id == session.id,
        SplitBillItemAssignment.participant_id == participant_id,
    ).delete(synchronize_session=False)

    for item_id, quantity in requested.items():
        if quantity <= QUANTITY_TOLERANCE:
            continue
        item = item_by_id[item_id]
        db.add(
            SplitBillItemAssignment(
                session_id=session.id,
                participant_id=participant_id,
                receipt_item_id=item.id,
                quantity=round(quantity, 3),
                amount=_amount_for_quantity(item, quantity),
            )
        )

    db.commit()
    return get_split_bill_session_summary(db, session)


def close_split_bill_session(
    db: Session,
    session: SplitBillSession,
    owner_user_id: int,
) -> dict:
    if session.owner_user_id != owner_user_id:
        raise ValueError("Only the bill owner can close this session.")

    summary = get_split_bill_session_summary(db, session)
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
        "message": "Split bill session was closed successfully.",
    }


def update_expected_participants_count(
    db: Session,
    session: SplitBillSession,
    owner_user_id: int,
    expected_participants_count: int,
) -> dict:
    if session.status != "open":
        raise ValueError("This split bill session is closed.")
    if session.owner_user_id != owner_user_id:
        raise ValueError("Only the bill owner can change the participant count.")

    joined_count = get_joined_participants_count(db, session)
    if expected_participants_count < joined_count:
        raise ValueError(
            f"Participant count cannot be lower than {joined_count}, because those participants have already joined."
        )
    if expected_participants_count > 20:
        raise ValueError("Participant count cannot be greater than 20.")

    session.expected_participants_count = expected_participants_count
    db.commit()
    db.refresh(session)
    return get_split_bill_session_summary(db, session)
