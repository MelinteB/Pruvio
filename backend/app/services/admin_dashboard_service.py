"""Explicit database console policy. No SQL or table names supplied by clients are executed."""
import csv
import hashlib
import io
import json
import math
from datetime import datetime
from sqlalchemy import String, Text, Boolean, Integer, Float, DateTime, or_, cast
from sqlalchemy.exc import IntegrityError
from app.db.database import Base, SessionLocal
from app.models.user import User
from app.models.admin_audit import AdminAudit
from app.schemas.user import UserAdminUpdate
from app.services.user_service import update_user_admin

# Every application model is visible, but each writable field is explicitly approved.
EDITABLE = {
    "users": set(UserAdminUpdate.model_fields) - {"is_admin"},
    "cases": {"module"},
    "documents": {"document_type", "original_filename", "ocr_text"},
    "receipt_items": {"name", "translated_name", "source_language", "quantity", "unit_price", "total_price", "currency"},
    "receipt_profiles": {"merchant_name", "merchant_tax_id", "country", "profile_name", "rules_json"},
    "receipt_corrections": {"notes"},
    "reminders": {"due_date"},
    "split_bill_sessions": {"expected_participants_count", "tip_mode", "tip_value"},
    "split_bill_participants": {"display_name"},
    "passkey_credentials": {"device_name"},
}
HIDDEN = {"password_hash", "username_key", "token", "participant_token", "token_hash", "claim_hash",
          "code_hash", "code_ciphertext", "challenge_id", "credential_id", "public_key", "context_value"}
# Explicit projections for authentication-related models: never leak future secret fields.
SECURITY_FIELDS = {
    "verification_codes": {"id", "user_id", "purpose", "destination_type", "delivery_channel", "delivery_status", "status", "attempts", "max_attempts", "created_at", "expires_at", "verified_at"},
    "trusted_devices": {"id", "user_id", "created_at", "expires_at", "revoked_at"},
    "passkey_credentials": {"id", "user_id", "device_name", "device_type", "transports", "backed_up", "sign_count", "created_at", "last_used_at"},
}
LABELS = {"users":"Users", "cases":"Receipt cases", "documents":"Documents & OCR text", "receipt_items":"Receipt items",
          "split_bill_sessions":"Split bills", "split_bill_participants":"Participants", "split_bill_item_assignments":"Item selections",
          "external_ocr_requests":"OCR requests", "external_ocr_usage":"OCR usage", "receipt_profiles":"Receipt profiles",
          "receipt_corrections":"Receipt corrections", "admin_audit":"Administration activity"}


def require_admin(db, actor_id):
    # Always fetch the current database role, including on existing websocket callbacks.
    user = db.get(User, actor_id, populate_existing=True) if actor_id else None
    if not user or user.status != "active" or not user.is_admin:
        raise PermissionError("Administrator access is required. Sign in with an active admin account.")
    return user


def current_admin_id():
    from app.ui.auth_state import get_logged_in_user_id
    try:
        with SessionLocal() as db:
            return require_admin(db, get_logged_in_user_id()).id
    except (PermissionError, RuntimeError):
        return None


def models():
    return {m.local_table.name: m.class_ for m in Base.registry.mappers}


def model_for(entity):
    model = models().get(entity)
    if model is None:
        raise ValueError("Unknown record category.")
    return model


def visible_columns(model):
    table = model.__table__
    return [c for c in table.columns if c.name not in HIDDEN and
            (table.name not in SECURITY_FIELDS or c.name in SECURITY_FIELDS[table.name])]


def serialize(row):
    result = {}
    for c in visible_columns(type(row)):
        value = getattr(row, c.name)
        result[c.name] = value.isoformat() if isinstance(value, datetime) else value
    return result


def revision(row):
    raw = {c.name: str(getattr(row, c.name)) for c in row.__table__.columns}
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


def add_audit(db, actor_id, source, action, entity, record_id, fields=()):
    db.add(AdminAudit(actor_user_id=actor_id, source=source, action=action, entity=entity,
                      record_id=record_id, changed_fields=json.dumps(sorted(fields))))


def catalog(db, actor_id):
    require_admin(db, actor_id)
    return [{"key": name, "label": LABELS.get(name, name.replace("_", " ").title()),
             "count": db.query(model).count(), "editable": bool(EDITABLE.get(name))}
            for name, model in sorted(models().items())]


def list_records(db, actor_id, entity, search="", offset=0, limit=25, filter_field=None, filter_value=None, sort="id", descending=True):
    require_admin(db, actor_id)
    model = model_for(entity)
    columns = {c.name: c for c in visible_columns(model)}
    query = db.query(model)
    if search.strip():
        needle = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(*[cast(c, String).ilike(needle, escape="\\") for c in columns.values()]))
    if filter_field:
        if filter_field not in columns:
            raise ValueError("Unknown filter field.")
        query = query.filter(cast(columns[filter_field], String) == str(filter_value))
    if sort not in columns:
        raise ValueError("Unknown sort field.")
    order = columns[sort].desc() if descending else columns[sort].asc()
    total = query.count()
    rows = query.order_by(order, model.id).offset(max(0, int(offset))).limit(min(max(1, int(limit)), 500)).all()
    return total, [serialize(row) for row in rows]


def get_record(db, actor_id, entity, record_id):
    require_admin(db, actor_id)
    row = db.get(model_for(entity), record_id)
    if row is None:
        raise ValueError("Record no longer exists.")
    return serialize(row), revision(row)


def convert(column, value):
    if value is None:
        if not column.nullable:
            raise ValueError(f"{column.name} cannot be empty.")
        return None
    if isinstance(column.type, Boolean):
        if type(value) is not bool:
            raise ValueError(f"{column.name} must be true or false.")
        return value
    if isinstance(column.type, (Integer, Float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Numbers must be finite.")
        if isinstance(column.type, Integer):
            if not number.is_integer():
                raise ValueError("A whole number is required.")
            return int(number)
        return number
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(str(value))
    value = str(value)
    maximum = getattr(column.type, "length", None)
    if maximum and len(value) > maximum:
        raise ValueError(f"{column.name} exceeds {maximum} characters.")
    if column.name.endswith("_json"):
        json.loads(value)
    return value


def update_record(db, actor_id, entity, record_id, changes, expected_revision):
    require_admin(db, actor_id)
    model = model_for(entity)
    row = db.query(model).filter(model.id == record_id).with_for_update().first()
    if row is None:
        raise ValueError("Record no longer exists.")
    if not expected_revision or revision(row) != expected_revision:
        raise ValueError("This record changed. Close this form and open it again before saving.")
    if set(changes) - EDITABLE.get(entity, set()):
        raise ValueError("One or more fields are read-only. Admin roles can only be changed through the admin-key API.")
    if not changes:
        return
    clean = {name: convert(model.__table__.c[name], value) for name, value in changes.items()}
    if entity == "users":
        if record_id == actor_id and clean.get("status", "active") != "active":
            raise ValueError("Use the admin-key API to deactivate your own administrator account.")
        add_audit(db, actor_id, "dashboard", "update", entity, record_id, clean)
        update_user_admin(db, row, UserAdminUpdate(**clean))
        return
    if entity == "split_bill_sessions":
        if row.status != "open":
            raise ValueError("Only open split bills can be edited. The owner must reopen settled bills first.")
        participants = model_for("split_bill_participants")
        joined = db.query(participants).filter(participants.session_id == row.id, participants.status == "joined").count()
        count = clean.get("expected_participants_count", row.expected_participants_count)
        if not max(1, joined) <= count <= 20:
            raise ValueError(f"Participant count must be between {max(1, joined)} and 20.")
        mode = clean.get("tip_mode", row.tip_mode)
        value = clean.get("tip_value", row.tip_value)
        if mode not in {"none", "percent", "fixed"} or value < 0 or (mode == "percent" and value > 100):
            raise ValueError("Use none, percent (0–100), or fixed with a nonnegative tip value.")
        if mode == "none":
            clean["tip_value"] = 0.0
    if entity == "receipt_items":
        if set(clean) & {"quantity", "unit_price", "total_price", "currency"}:
            session = model_for("split_bill_sessions")
            if db.query(session.id).filter(session.case_id == row.case_id).first():
                raise ValueError("Amounts and currency are locked because this receipt has a split bill. Names and translations can still be corrected.")
            if float(clean.get("quantity", row.quantity)) <= 0:
                raise ValueError("Quantity must be greater than zero.")
            currency = str(clean.get("currency", row.currency)).upper().strip()
            if len(currency) != 3 or not currency.isalpha():
                raise ValueError("Currency must be a three-letter code, for example RON.")
            clean["currency"] = currency
    for name, value in clean.items():
        setattr(row, name, value)
    if hasattr(row, "updated_at"):
        row.updated_at = datetime.utcnow()
    add_audit(db, actor_id, "dashboard", "update", entity, record_id, clean)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ValueError("The change conflicts with an existing record or a required relationship.") from error


def related_records(db, actor_id, entity, record_id):
    require_admin(db, actor_id)
    model = model_for(entity)
    row = db.get(model, record_id)
    if row is None:
        raise ValueError("Record no longer exists.")
    links = []
    for c in visible_columns(model):
        for fk in c.foreign_keys:
            value = getattr(row, c.name)
            if value is not None:
                links.append((fk.column.table.name, "id", value, f"Open {c.name.replace('_id', '').replace('_', ' ')} #{value}"))
    for name, other in models().items():
        for c in visible_columns(other):
            for fk in c.foreign_keys:
                if fk.column.table.name == entity:
                    count = db.query(other).filter(c == record_id).count()
                    if count:
                        links.append((name, c.name, record_id, f"{LABELS.get(name, name.replace('_', ' ').title())} ({count})"))
    return links


def export_csv(db, actor_id, entity, **filters):
    total, _ = list_records(db, actor_id, entity, limit=1, **filters)
    if total > 10000:
        raise ValueError("Export is limited to 10,000 records. Narrow the search or filter first.")
    output = io.StringIO()
    fields = [c.name for c in visible_columns(model_for(entity))]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for offset in range(0, total, 500):
        _, rows = list_records(db, actor_id, entity, offset=offset, limit=500, **filters)
        for row in rows:
            # Prevent spreadsheet formula execution, including leading whitespace.
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v) for k, v in row.items()})
    add_audit(db, actor_id, "dashboard", "export", entity, None)
    db.commit()
    return output.getvalue().encode("utf-8-sig")


def user_bill_query(db, user_id):
    case = model_for('cases')
    session = model_for('split_bill_sessions')
    participant = model_for('split_bill_participants')
    participant_sessions = db.query(participant.session_id).filter(participant.user_id == user_id)
    linked_cases = db.query(session.case_id).filter(or_(session.owner_user_id == user_id, session.id.in_(participant_sessions)))
    return db.query(case).filter(or_(case.user_id == user_id, case.id.in_(linked_cases)))


def list_user_bills(db, actor_id, user_id, offset=0, limit=20):
    """One row per saved receipt case; include failed/empty receipts and participation."""
    require_admin(db, actor_id)
    if not db.get(User, user_id):
        raise ValueError('User no longer exists.')
    from app.services.standalone_app_service import get_receipt_view
    query = user_bill_query(db, user_id)
    case_model = model_for('cases')
    session_model = model_for('split_bill_sessions')
    participant_model = model_for('split_bill_participants')
    rows = []
    for case in query.order_by(case_model.created_at.desc(), case_model.id.desc()).offset(max(0,offset)).limit(min(100,max(1,limit))):
        receipt = get_receipt_view(db, case.id, ensure_translations=False)
        sessions = db.query(session_model).filter(session_model.case_id == case.id).order_by(session_model.id).all()
        mine = db.query(participant_model).filter(participant_model.user_id == user_id, participant_model.session_id.in_([s.id for s in sessions])).all() if sessions else []
        roles = []
        if case.user_id == user_id:
            roles.append('Receipt owner')
        if any(s.owner_user_id == user_id for s in sessions):
            roles.append('Bill owner')
        elif mine:
            roles.append('Participant')
        rows.append({
            'case_id':case.id, 'merchant':receipt['merchant_name'], 'role':', '.join(roles),
            'receipt_status':case.status, 'split_status':', '.join(f"#{s.id}: {s.status}" for s in sessions) or 'Not split',
            'payment_status':', '.join(f"#{p.session_id}: {p.payment_status or 'unpaid'}" for p in mine) or '—',
            'total':receipt['receipt_total'], 'currency':receipt['currency'],
            'created_at':case.created_at.isoformat() if case.created_at else None,
        })
    return query.count(), rows


def user_bill_details(db, actor_id, user_id, case_id):
    require_admin(db, actor_id)
    case = user_bill_query(db,user_id).filter(model_for('cases').id == case_id).first()
    if case is None:
        raise ValueError('This bill is not linked to the selected user.')
    from app.services.standalone_app_service import get_receipt_view
    from app.services.split_bill_session_service import get_split_bill_session_summary
    session_model = model_for('split_bill_sessions')
    splits = []
    for session in db.query(session_model).filter(session_model.case_id == case_id).order_by(session_model.id):
        summary = get_split_bill_session_summary(db, session, ensure_translations=False)
        for key in ('token','share_url','qr_url'):
            summary.pop(key,None)
        summary['record'] = serialize(session)
        # Include invited/left/non-joined participants as well as the calculated joined summaries.
        participant_model = model_for('split_bill_participants')
        summary['all_participant_records'] = [serialize(p) for p in db.query(participant_model).filter(participant_model.session_id == session.id).order_by(participant_model.id)]
        names = {p['id']:p['display_name'] for p in summary['all_participant_records']}
        for item in summary['items']:
            for assignment in item['assignments']:
                assignment['assigned_to'] = names.get(assignment['participant_id'], assignment['assigned_to'])
        assignment_model = model_for('split_bill_item_assignments')
        summary['assignment_records'] = [serialize(a) for a in db.query(assignment_model).filter(assignment_model.session_id == session.id).order_by(assignment_model.id)]
        splits.append(summary)
    result = {'case':serialize(case), 'receipt':get_receipt_view(db,case_id,ensure_translations=False), 'splits':splits}
    for entity in ('receipt_items','documents','external_ocr_requests','external_ocr_usage','receipt_corrections','messages','reminders'):
        model = model_for(entity)
        result[entity] = [serialize(r) for r in db.query(model).filter(model.case_id == case_id).order_by(model.id)]
    return result
