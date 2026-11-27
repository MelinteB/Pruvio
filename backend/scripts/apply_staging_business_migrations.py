"""Apply the release's additive Business migrations to staging only.

This is used by the staging Render start command because free instances do not
support shell sessions or one-off jobs. It intentionally refuses every other
database and only reads the three reviewed migration files below.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from argon2 import PasswordHasher
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
    (
        "b17_0726_program_scoped_pilot_approval.sql",
        ("merchant_program_pilot_enrollment_v0726", "merchant_program_pilot_audit_v0726"),
    ),
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


def _database_identity(engine) -> tuple[str, str | None]:
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT current_database(), inet_server_addr()::text"
        )).one()
        return row[0], row[1]


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
        business_engine = create_engine(business_url, pool_pre_ping=True)
        migration_engine = create_engine(migration_url, pool_pre_ping=True)
        try:
            business_identity = _database_identity(business_engine)
            migration_identity = _database_identity(migration_engine)
            if business_identity != migration_identity:
                raise RuntimeError(
                    "Refusing migration: temporary credential connects to a different database server"
                )
            if not _has_schema_create(migration_engine):
                raise RuntimeError(
                    "Temporary staging migration role cannot create tables in public"
                )
        except Exception:
            business_engine.dispose()
            migration_engine.dispose()
            raise
        business_engine.dispose()
        return migration_engine, business_role, True

    # After the one-time migration credential is removed, the least-privilege
    # Business app role can still verify existing migrations on each restart.
    business_engine = create_engine(business_url, pool_pre_ping=True)
    return business_engine, business_role, False


def _bootstrap_staging_admin(engine) -> None:
    """Create at most one explicitly requested staging platform admin.

    Render invokes this migration script at service startup. Provisioning runs
    only when both temporary Render environment variables are present and only
    against the isolated Business staging database. Remove both variables after
    the first successful deploy.
    """
    email = os.getenv("PRUVS_STAGING_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("PRUVS_STAGING_ADMIN_PASSWORD", "")
    if not email and not password:
        return
    if not email or not password:
        print(
            "Staging admin bootstrap skipped: set both temporary admin variables.",
            flush=True,
        )
        return
    if os.getenv("PRUVS_PLATFORM_COMBINED_STAGING", "").lower() != "true":
        raise RuntimeError("Refusing admin bootstrap: combined staging mode is not enabled")
    business_url = _normalized_url(os.getenv("BUSINESS_DATABASE_URL", "").strip())
    if (
        business_url.database != EXPECTED_DATABASE
        or business_url.username != "pruvs_business_stage"
    ):
        raise RuntimeError(
            "Refusing admin bootstrap: expected the isolated staging Business database role"
        )
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise RuntimeError("Refusing admin bootstrap: invalid admin email")
    if len(password) < 20 or len(password) > 256:
        raise RuntimeError("Refusing admin bootstrap: password must be 20 to 256 characters")

    # Serialize the one-time check-and-create so two concurrent service starts
    # cannot create separate platform admins.
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key_a, :key_b)"),
            {"key_a": 76114621, "key_b": 612},
        )
        existing_admin = connection.execute(
            text("SELECT id FROM merchant_staff WHERE role = 'platform_admin' LIMIT 1")
        ).scalar_one_or_none()
        if existing_admin:
            print(
                "Staging admin bootstrap skipped: a platform admin already exists.",
                flush=True,
            )
            return
        existing_email = connection.execute(
            text("SELECT id FROM merchant_staff WHERE lower(email) = :email LIMIT 1"),
            {"email": email},
        ).scalar_one_or_none()
        if existing_email:
            print(
                "Staging admin bootstrap skipped: the email is already in use.",
                flush=True,
            )
            return

        operations_name = "Pruvs Platform Operations (staging)"
        merchant_id = connection.execute(
            text("SELECT id FROM merchants WHERE name = :name LIMIT 1"),
            {"name": operations_name},
        ).scalar_one_or_none()
        if merchant_id is None:
            merchant_id = str(uuid.uuid4())
            connection.execute(
                text(
                    "INSERT INTO merchants (id, name, status, created_at) "
                    "VALUES (:id, :name, 'active', :created_at)"
                ),
                {
                    "id": merchant_id,
                    "name": operations_name,
                    "created_at": datetime.now(timezone.utc),
                },
            )

        connection.execute(
            text(
                "INSERT INTO merchant_staff "
                "(id, merchant_id, email, password_hash, role, active) "
                "VALUES (:id, :merchant_id, :email, :password_hash, "
                "'platform_admin', TRUE)"
            ),
            {
                "id": str(uuid.uuid4()),
                "merchant_id": merchant_id,
                "email": email,
                "password_hash": PasswordHasher().hash(password),
            },
        )

    print("Created one staging platform admin from temporary Render variables.", flush=True)


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
        _bootstrap_staging_admin(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
