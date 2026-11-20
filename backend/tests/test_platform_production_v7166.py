from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_entrypoint_preserves_database_separation_and_never_migrates_on_startup():
    code = (ROOT / 'app/platform_production.py').read_text(encoding='utf-8')
    assert 'APP_ENV' in code and 'production' in code
    assert 'DATABASE_URL' in code and 'BUSINESS_DATABASE_URL' in code
    assert 'PRUVS_PLATFORM_COMBINED_PRODUCTION' in code
    assert 'separate logical databases' in code
    assert 'app.mount("/business"' in code
    assert 'app.mount("/"' in code
    assert 'create_all' not in code
    assert 'alembic' not in code.lower()
    assert 'MerchantStorePlace.__table__.create' not in code


def test_combined_production_routes_business_to_its_separate_database():
    config = (ROOT / 'business/config.py').read_text(encoding='utf-8')
    assert "combined_production = os.getenv('PRUVS_PLATFORM_COMBINED_PRODUCTION'" in config
    assert "db_url = os.environ.get('BUSINESS_DATABASE_URL'" in config
