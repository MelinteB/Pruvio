"""Production combined-service configuration tests: no network or DB connections."""
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.engine import make_url

from business.config import get_settings
from app.react_app import loyalty_gateway

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_entrypoint_has_separate_mounted_apps_and_database_guardrails():
    source = (BACKEND / "app" / "platform_production.py").read_text(encoding="utf-8")
    ast.parse(source)
    for key in ("PRUVS_PLATFORM_COMBINED_PRODUCTION",
                "PRUVS_PLATFORM_COMBINED_STAGING",
                "PRUVS_PRODUCTION_CORE_DB_NAME",
                "PRUVS_PRODUCTION_BUSINESS_DB_NAME",
                "BUSINESS_DATABASE_URL"):
        assert key in source
    assert source.index('app.mount("/business"') < source.index('app.mount("/", core_app')


def configure(monkeypatch, business_db="pruvs_business", driver="postgresql"):
    monkeypatch.setenv("PRUVS_PLATFORM_COMBINED_PRODUCTION", "true")
    monkeypatch.delenv("PRUVS_PLATFORM_COMBINED_STAGING", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PRUVS_PRODUCTION_BUSINESS_DB_NAME", "pruvs_business")
    monkeypatch.setenv("BUSINESS_DATABASE_URL", f"{driver}://merchant:pass@db.example.invalid/{business_db}")
    monkeypatch.setenv("BUSINESS_JWT_SECRET", "j" * 40)
    monkeypatch.setenv("PRUVS_BRIDGE_SECRET", "r" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "https://pruvs.io")


def test_production_business_normalizes_render_postgresql_url(monkeypatch):
    configure(monkeypatch)
    db = make_url(get_settings().database_url)
    assert db.drivername == "postgresql+psycopg"
    assert db.database == "pruvs_business"
    assert db.username == "merchant"


@pytest.mark.parametrize("database,driver", [
    ("pruvs_core", "postgresql"),
    ("pruvs_business_staging", "postgresql"),
    ("pruvs_business", "sqlite"),
])
def test_production_business_fails_closed_on_wrong_db_or_driver(monkeypatch, database, driver):
    configure(monkeypatch, database, driver)
    with pytest.raises((RuntimeError, ValueError)):
        get_settings()


def test_production_business_requires_approved_db_name(monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("PRUVS_PRODUCTION_BUSINESS_DB_NAME")
    with pytest.raises(RuntimeError):
        get_settings()


def test_staging_and_production_flags_are_exclusive(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("PRUVS_PLATFORM_COMBINED_STAGING", "true")
    with pytest.raises(RuntimeError):
        get_settings()


def test_production_business_requires_production_environment(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(RuntimeError):
        get_settings()


def test_production_loyalty_gateway_uses_fixed_loopback(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("PRUVS_LOYALTY_ENABLED", "true")
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("PRUVS_BUSINESS_API_URL", "https://external.invalid")
    base, secret = loyalty_gateway.config()
    assert base == "http://127.0.0.1:10000/business"
    assert len(secret) == 40


def test_production_loyalty_gateway_rejects_invalid_port(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("PRUVS_LOYALTY_ENABLED", "true")
    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(HTTPException) as exc:
        loyalty_gateway.config()
    assert exc.value.status_code == 503
