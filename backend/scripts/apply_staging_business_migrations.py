"""Apply the release's additive Business migrations to staging only.

This is used by the staging Render start command because free instances do not
support shell sessions or one-off jobs. It intentionally refuses every other
database and only reads the three reviewed migration files below.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


EXPECTED_DATABASE = "pruvs_business_staging"
MIGRATION_DIR = Path(__file__).resolve().parents[1] / "business_migrations" / "versions"
MIGRATIONS = (
    ("b14a0624_campaign_gallery.sql", ("loyalty_promotion_gallery_v0624",)),
    (
        "b15a0624_management.sql",
        ("merchant_location_archives_v0624", "merchant_management_audit_v0624"),
    ),
    ("b16a0725_campaign_media_registry.sql", ("loyalty_campaign_media_v0725",)),
)


def _database_engine():
    if os.getenv("PRUVS_PLATFORM_COMBINED_STAGING", "").lower() != "true":
        raise RuntimeError("Refusing migration: combined staging mode is not enabled")

    raw_url = os.getenv("BUSINESS_DATABASE_URL", "").strip()
    if not raw_url:
        raise RuntimeError("Refusing migration: BUSINESS_DATABASE_URL is missing")

    parsed = make_url(raw_url)
    if parsed.drivername not in {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
        raise RuntimeError("Refusing migration: Business database must be PostgreSQL")
    if parsed.database != EXPECTED_DATABASE:
        raise RuntimeError("Refusing migration: database is not the isolated staging Business database")
    if not parsed.host:
        raise RuntimeError("Refusing migration: database host is missing")

    url = parsed.set(drivername="postgresql+psycopg")
    return create_engine(url, pool_pre_ping=True)


def _statements(path: Path) -> list[str]:
    sql_lines = [
        line.split("--", 1)[0]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    sql = "\n".join(sql_lines)
    statements = []
    for statement in sql.split(";"):
        statement = statement.strip()
        if not statement or statement.upper() in {"BEGIN", "COMMIT"}:
            continue
        statements.append(statement)
    if not statements or any(not item.upper().startswith(("CREATE TABLE", "CREATE INDEX")) for item in statements):
        raise RuntimeError(f"Refusing unexpected SQL in migration {path.name}")
    return statements


def main() -> None:
    engine = _database_engine()
    try:
        with engine.connect() as connection:
            existing = inspect(connection)
            missing_base = [
                table
                for table in ("loyalty_promotions", "stores")
                if not existing.has_table(table)
            ]
            if missing_base:
                raise RuntimeError(
                    "Refusing migration: required Business tables are missing: "
                    + ", ".join(missing_base)
                )

        for filename, sentinels in MIGRATIONS:
            path = MIGRATION_DIR / filename
            if not path.is_file():
                raise RuntimeError(f"Required migration file is missing: {filename}")
            with engine.connect() as connection:
                if all(inspect(connection).has_table(table) for table in sentinels):
                    print(f"Migration already present: {filename}", flush=True)
                    continue
            with engine.begin() as connection:
                for statement in _statements(path):
                    connection.execute(text(statement))
            with engine.connect() as connection:
                if not all(inspect(connection).has_table(table) for table in sentinels):
                    raise RuntimeError(f"Migration verification failed: {filename}")
            print(f"Applied and verified: {filename}", flush=True)

        print(f"Staging Business schema ready in {EXPECTED_DATABASE}", flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
