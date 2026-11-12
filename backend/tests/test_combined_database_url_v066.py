"""Regression tests for Render's standard PostgreSQL URL and strict combined staging boundary.

No external database connection, environment secrets, or database migrations are used.
"""
from functools import lru_cache
import pytest
from sqlalchemy.engine import make_url
from business.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_combined_business_accepts_render_standard_postgresql_url(monkeypatch):
    monkeypatch.setenv('PRUVS_PLATFORM_COMBINED_STAGING', 'true')
    monkeypatch.setenv('BUSINESS_DATABASE_URL',
                       'postgresql://pruvs_business_stage:example%40pass@db.example.invalid:5432/pruvs_business_staging')
    monkeypatch.setenv('BUSINESS_JWT_SECRET', 'b' * 40)
    monkeypatch.setenv('PRUVS_BRIDGE_SECRET', 'r' * 40)
    monkeypatch.setenv('APP_ENV', 'development')
    settings = get_settings()
    url = make_url(settings.database_url)
    assert url.drivername == 'postgresql+psycopg'
    assert url.database == 'pruvs_business_staging'
    assert url.username == 'pruvs_business_stage'
    assert url.password == 'example@pass'


def test_combined_business_accepts_explicit_psycopg_v3_url(monkeypatch):
    monkeypatch.setenv('PRUVS_PLATFORM_COMBINED_STAGING', 'true')
    monkeypatch.setenv('BUSINESS_DATABASE_URL',
                       'postgresql+psycopg://pruvs_business_stage:example@db.example.invalid/pruvs_business_staging')
    monkeypatch.setenv('BUSINESS_JWT_SECRET', 'b' * 40)
    monkeypatch.setenv('PRUVS_BRIDGE_SECRET', 'r' * 40)
    assert get_settings().database_url.startswith('postgresql+psycopg://')


@pytest.mark.parametrize('url', [
    'sqlite:///tmp/business.db',
    'postgresql://staging:sample@db.example.invalid/pruvs_core_staging',
    'postgresql://staging:sample@db.example.invalid/pruvs_business',
    'mysql://staging:sample@db.example.invalid/pruvs_business_staging',
    'this is not a database URL',
])
def test_combined_business_rejects_wrong_database_or_scheme(monkeypatch, url):
    monkeypatch.setenv('PRUVS_PLATFORM_COMBINED_STAGING', 'true')
    monkeypatch.setenv('BUSINESS_DATABASE_URL', url)
    monkeypatch.setenv('BUSINESS_JWT_SECRET', 'b' * 40)
    monkeypatch.setenv('PRUVS_BRIDGE_SECRET', 'r' * 40)
    with pytest.raises(RuntimeError):
        get_settings()
