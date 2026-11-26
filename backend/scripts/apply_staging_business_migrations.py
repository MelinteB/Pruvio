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


def _normalized_url(raw_url: str):
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
    if not parsed.username:
        raise RuntimeError("Refusing migration: database role is missing")
    return parsed.set(drivername="postgresql+psycopg")


def _render_host_identity(host: str) -> str:
    normalized = host.rstrip(".").lower()
    external_suffix = ".frankfurt-postgres.render.com"
    if normalized.endswith(external_suffix):
        return normalized[: -len(external_suffix)]
    return normalized


def _has_schema_create(engine) -> bool:
    with engine.connect() as connection:
        return bool(connection.execute(text(
            "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
        )).scalar_one())


def _database_engine():
    if os.getenv("PRUVS_PLATFORM_COMBINED_STAGING", "").lower() != "true":
        raise RuntimeError("Refusing migration: combined staging mode is not enabled")

    raw_url = os.getenv("BUSINESS_DATABASE_URL", "").strip()
    if not raw_url:
        raise RuntimeError("Refusing migration: BUSINESS_DATABASE_URL is missing")

    business_url = _normalized_url(raw_url)
    business_role = business_url.username

    # A short-lived Render environment variable may supply the database-owner
    # credential for the one-time staging DDL. It is accepted only for this
    # exact staging database on the same Postgres host and port as the Business
    # URL. Remove it from Render immediately after verified migration.
    migration_raw_url = os.getenv("PRUVS_STAGING_MIGRATION_DATABASE_URL", "").strip()
    if migration_raw_url:
        migration_url = _normalized_url(migration_raw_url)
        if (
            _render_host_identity(migration_url.host) != _render_host_identity(business_url.host)
            or migration_url.port != business_url.port
        ):
            raise RuntimeError(
                "Refusing migration: temporary migration credential is not on the same Render Postgres instance"
            )
        migration_engine = create_engine(migration_url, pool_pre_ping=True)
        try:
            if not _has_schema_create(migration_engine):
                raise RuntimeError(
                    "Temporary staging migration role cannot create tables in public"
                )
        except Exception:
            migration_engine.dispose()
            raise
        return migration_engine, business_role, True

    # After the one-time migration credential is removed, the least-privilege
    # Business app role can still verify existing migrations on each restart.
    business_engine = create_engine(business_url, pool_pre_ping=True)
    return business_engine, business_role, False


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
    engine, business_role, using_temporary_owner = _database_engine()
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

        can_create = _has_schema_create(engine)
        for filename, sentinels in MIGRATIONS:
            path = MIGRATION_DIR / filename
            if not path.is_file():
                raise RuntimeError(f"Required migration file is missing: {filename}")
            with engine.connect() as connection:
                if all(inspect(connection).has_table(table) for table in sentinels):
                    print(f"Migration already present: {filename}", flush=True)
                    continue
            if not can_create:
                raise RuntimeError(
                    f"Migration {filename} is missing and the Business app role lacks DDL permission"
                )
            with engine.begin() as connection:
                for statement in _statements(path):
                    connection.execute(text(statement))
            with engine.connect() as connection:
                if not all(inspect(connection).has_table(table) for table in sentinels):
                    raise RuntimeError(f"Migration verification failed: {filename}")
            print(f"Applied and verified: {filename}", flush=True)

        # The temporary database-owner role grants only table-level CRUD access
        # to the least-privilege Business app role.
        if using_temporary_owner:
            role_identifier = engine.dialect.identifier_preparer.quote(business_role)
            table_names = tuple(table for _, sentinels in MIGRATIONS for table in sentinels)
            with engine.begin() as connection:
                for table in table_names:
                    quoted_table = engine.dialect.identifier_preparer.quote(table)
                    connection.execute(text(
                        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {quoted_table} TO {role_identifier}"
                    ))

        print(f"Staging Business schema ready in {EXPECTED_DATABASE}", flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
