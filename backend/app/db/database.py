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
            "email": "VARCHAR(255)",
            "password_hash": "VARCHAR(512)",
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

    if not migrations:
        return

    with engine.begin() as connection:
        for statement in migrations:
            connection.execute(text(statement))
