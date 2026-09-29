import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


ENV_PATH = BACKEND_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL is missing.")
    print("Set it first with:")
    print('$env:DATABASE_URL="PASTE_RENDER_EXTERNAL_DATABASE_URL_HERE"')
    sys.exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = DATABASE_URL

if not DATABASE_URL.startswith("postgresql://"):
    print("ERROR: This script is only for PostgreSQL.")
    print(f"Current DATABASE_URL starts with: {DATABASE_URL.split(':')[0]}")
    print("Aborting to avoid cleaning SQLite by mistake.")
    sys.exit(1)


from app.db.database import engine  # noqa: E402


KEEP_USERS = True


TABLES_TO_CLEAN_KEEP_USERS = [
    "split_bill_item_assignments",
    "split_bill_participants",
    "split_bill_sessions",
    "receipt_items",
    "external_ocr_requests",
    "external_ocr_usage",
    "verification_codes",
    "documents",
    "messages",
    "reminders",
    "cases",
]


TABLES_TO_CLEAN_WITH_USERS = TABLES_TO_CLEAN_KEEP_USERS + [
    "users",
]


def clean_database():
    print("Connected database dialect:", engine.dialect.name)

    if engine.dialect.name != "postgresql":
        print("ERROR: SQLAlchemy is not connected to PostgreSQL.")
        print("Aborting.")
        sys.exit(1)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if KEEP_USERS:
        print("Mode: keep users")
        requested_tables = TABLES_TO_CLEAN_KEEP_USERS
    else:
        print("Mode: delete everything including users")
        requested_tables = TABLES_TO_CLEAN_WITH_USERS

    tables = [
        table
        for table in requested_tables
        if table in existing_tables
    ]

    missing_tables = [
        table
        for table in requested_tables
        if table not in existing_tables
    ]

    print()
    print("Tables that will be cleaned:")
    for table in tables:
        print(f"- {table}")

    if missing_tables:
        print()
        print("Tables not found, skipped:")
        for table in missing_tables:
            print(f"- {table}")

    if not tables:
        print("No matching tables found. Nothing to clean.")
        return

    print()
    print("WARNING: This will delete test data from Render Postgres.")
    confirmation = input('Type CLEAN to continue: ').strip()

    if confirmation != "CLEAN":
        print("Aborted. Nothing was deleted.")
        return

    truncate_sql = text(
        "TRUNCATE TABLE "
        + ", ".join(tables)
        + " RESTART IDENTITY CASCADE;"
    )

    with engine.begin() as connection:
        connection.execute(truncate_sql)

    print()
    print("Done. Render Postgres database cleaned.")

    if KEEP_USERS:
        print("Users were kept.")
    else:
        print("Users were also deleted.")


if __name__ == "__main__":
    clean_database()