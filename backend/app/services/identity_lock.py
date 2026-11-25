"""Serialize normalized email creation across registration paths in PostgreSQL."""
from sqlalchemy import text

def lock_email(db, email):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:email, 7167))"),
                   {"email": str(email).strip().lower()})
