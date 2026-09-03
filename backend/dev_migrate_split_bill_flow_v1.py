import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "pruvio.db"


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return column_name in [row[1] for row in cursor.fetchall()]


def add_column(cursor, table_name: str, column_name: str, definition: str):
    if not column_exists(cursor, table_name, column_name):
        print(f"Adding {table_name}.{column_name}")
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )
    else:
        print(f"Already exists: {table_name}.{column_name}")


def main():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Start the backend once so SQLAlchemy can create the database.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    add_column(
        cursor,
        "split_bill_sessions",
        "owner_user_id",
        "INTEGER"
    )

    add_column(
        cursor,
        "split_bill_sessions",
        "expected_participants_count",
        "INTEGER DEFAULT 2"
    )

    add_column(
        cursor,
        "split_bill_sessions",
        "closed_at",
        "DATETIME"
    )

    add_column(
        cursor,
        "split_bill_participants",
        "user_id",
        "INTEGER"
    )

    add_column(
        cursor,
        "split_bill_participants",
        "phone_number",
        "VARCHAR"
    )

    add_column(
        cursor,
        "split_bill_participants",
        "role",
        "VARCHAR DEFAULT 'participant'"
    )

    add_column(
        cursor,
        "split_bill_participants",
        "status",
        "VARCHAR DEFAULT 'joined'"
    )

    conn.commit()
    conn.close()

    print("Migration completed.")


if __name__ == "__main__":
    main()