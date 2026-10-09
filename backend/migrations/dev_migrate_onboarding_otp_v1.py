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
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    add_column(cursor, "users", "email", "VARCHAR")
    add_column(cursor, "users", "is_phone_verified", "BOOLEAN DEFAULT 0")
    add_column(cursor, "users", "is_email_verified", "BOOLEAN DEFAULT 0")

    conn.commit()
    conn.close()

    print("OTP onboarding migration completed.")


if __name__ == "__main__":
    main()