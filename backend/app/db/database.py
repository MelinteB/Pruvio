import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pruvio.db")

# Render/Postgres sometimes provides postgres://, while SQLAlchemy expects postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_compatibility_schema() -> None:
    """Small idempotent compatibility migrations for the current MVP."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    migrations: list[str] = []

    if "users" in table_names:
        cols = {c["name"] for c in inspector.get_columns("users")}
        wanted = {
            "username": "VARCHAR(80)",
            "username_key": "VARCHAR(255)",
            "email": "VARCHAR(255)",
            "password_hash": "VARCHAR(512)",
            "revolut_payment_link": "VARCHAR(500)",
            "payment_recipient_name": "VARCHAR(255)",
            "payment_iban": "VARCHAR(64)",
            "payment_bank_name": "VARCHAR(255)",
            "payment_bic": "VARCHAR(32)",
            "payment_note": "VARCHAR(255)",
            "terms_version": "VARCHAR(50)",
            "accepted_privacy": "BOOLEAN DEFAULT FALSE",
            "accepted_privacy_at": "TIMESTAMP NULL",
            "privacy_version": "VARCHAR(50)",
            "marketing_opt_in": "BOOLEAN DEFAULT FALSE",
            "notifications_opt_in": "BOOLEAN DEFAULT TRUE",
            "preferred_language": "VARCHAR(12) DEFAULT 'en'",
            "updated_at": "TIMESTAMP NULL",
        }
        for name, sql_type in wanted.items():
            if name not in cols:
                migrations.append(f"ALTER TABLE users ADD COLUMN {name} {sql_type}")


    if "verification_codes" in table_names:
        cols = {c["name"] for c in inspector.get_columns("verification_codes")}
        wanted = {
            "challenge_id": "VARCHAR(64)", "code_ciphertext": "VARCHAR",
            "context_value": "VARCHAR(255)",
            "provider_message_id": "VARCHAR(255)", "delivery_channel": "VARCHAR(30)",
            "delivery_status": "VARCHAR(30)", "fallback_at": "TIMESTAMP NULL",
        }
        for name, sql_type in wanted.items():
            if name not in cols:
                migrations.append(f"ALTER TABLE verification_codes ADD COLUMN {name} {sql_type}")

    if "split_bill_sessions" in table_names:
        cols = {c["name"] for c in inspector.get_columns("split_bill_sessions")}
        wanted = {
            "tip_mode": "VARCHAR(20) DEFAULT 'none'",
            "tip_value": "DOUBLE PRECISION DEFAULT 0",
            "settled_at": "TIMESTAMP NULL",
        }
        for name, sql_type in wanted.items():
            if name not in cols:
                migrations.append(f"ALTER TABLE split_bill_sessions ADD COLUMN {name} {sql_type}")

    if "split_bill_participants" in table_names:
        cols = {c["name"] for c in inspector.get_columns("split_bill_participants")}
        wanted = {
            "reminder_message": "VARCHAR(500)",
            "reminder_at": "TIMESTAMP NULL",
            "payment_status": "VARCHAR(30) DEFAULT 'unpaid'",
            "payment_method": "VARCHAR(40)",
            "paid_at": "TIMESTAMP NULL",
        }
        for name, sql_type in wanted.items():
            if name not in cols:
                migrations.append(f"ALTER TABLE split_bill_participants ADD COLUMN {name} {sql_type}")

    if "receipt_items" in table_names:
        cols = {c["name"] for c in inspector.get_columns("receipt_items")}
        if "translated_name" not in cols:
            migrations.append("ALTER TABLE receipt_items ADD COLUMN translated_name VARCHAR(255)")
        if "source_language" not in cols:
            migrations.append("ALTER TABLE receipt_items ADD COLUMN source_language VARCHAR(12)")

    if "split_bill_item_assignments" in table_names:
        cols = {c["name"] for c in inspector.get_columns("split_bill_item_assignments")}
        if "quantity" not in cols:
            migrations.append("ALTER TABLE split_bill_item_assignments ADD COLUMN quantity DOUBLE PRECISION")

    with engine.begin() as connection:
        for statement in migrations:
            connection.execute(text(statement))
        if "users" in table_names:
            _backfill_usernames(connection)
        if "verification_codes" in table_names:
            code_cols = {c["name"] for c in inspect(connection).get_columns("verification_codes")}
            if {"destination_type", "status", "code_ciphertext"}.issubset(code_cols):
                connection.execute(text("UPDATE verification_codes SET status='expired', code_ciphertext=NULL "
                                        "WHERE destination_type='phone' AND status='pending'"))


def _backfill_usernames(connection) -> None:
    from app.usernames import normalize_username, username_key
    rows = connection.execute(text("SELECT id, name, username, username_key FROM users ORDER BY id")).mappings().all()
    used = {row["username_key"] for row in rows if row["username"] and row["username_key"]}
    for row in rows:
        if row["username"] and row["username_key"]:
            continue
        try:
            base = normalize_username(row["username"] or row["name"] or f"User {row['id']}")
        except ValueError:
            base = f"User {row['id']}"
        candidate = base
        suffix = 2
        while username_key(candidate) in used:
            ending = f" ({suffix})"
            candidate = base[:80-len(ending)].rstrip() + ending
            suffix += 1
        key = username_key(candidate)
        used.add(key)
        connection.execute(text("UPDATE users SET username=:username, username_key=:key WHERE id=:id"),
                           {"username": candidate, "key": key, "id": row["id"]})
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_key ON users (username_key)"))
