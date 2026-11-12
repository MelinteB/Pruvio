import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_env: str = 'development'
    database_url: str = 'sqlite:///./business.db'
    business_jwt_secret: str
    pruvs_bridge_secret: str
    cors_origins: str = 'http://localhost:5174'
    enable_demo_sandbox: bool = False
    demo_merchant_email: str = 'merchant@example.test'
    demo_merchant_password: str = ''

    @property
    def origins(self):
        return [x.strip() for x in self.cors_origins.split(',') if x.strip()]

    def validate_runtime(self):
        if len(self.business_jwt_secret) < 32 or len(self.pruvs_bridge_secret) < 32:
            raise ValueError('JWT and bridge secrets must each contain at least 32 characters')
        if self.business_jwt_secret == self.pruvs_bridge_secret:
            raise ValueError('Merchant and Pruvs bridge signing keys must be different')
        if self.app_env == 'production':
            if self.enable_demo_sandbox:
                raise ValueError('Demo sandbox cannot be enabled in production')
            if 'REPLACE' in self.business_jwt_secret.upper() or 'REPLACE' in self.pruvs_bridge_secret.upper():
                raise ValueError('Replace all example secrets before production')
            if not self.database_url.startswith('postgresql+psycopg://'):
                raise ValueError('Production requires PostgreSQL')
            if any('localhost' in x or '*' in x for x in self.origins):
                raise ValueError('Production CORS must list exact HTTPS origins')
            if any(not x.startswith('https://') for x in self.origins):
                raise ValueError('Production CORS must be HTTPS')

@lru_cache
def get_settings() -> Settings:
    if os.getenv('PRUVS_PLATFORM_COMBINED_STAGING','').lower() == 'true':
        db_url = os.environ.get('BUSINESS_DATABASE_URL','').strip()
        # Render supplies postgresql:// URLs by default. SQLAlchemy needs the
        # explicit psycopg v3 driver used by this application's dependencies.
        # Normalize only PostgreSQL schemes; never substitute the Core URL.
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import ArgumentError
        try:
            parsed = make_url(db_url)
        except (ArgumentError, ValueError) as exc:
            raise RuntimeError('Combined staging requires a valid Business PostgreSQL database URL') from exc
        if (parsed.drivername not in ('postgres', 'postgresql',
                                      'postgresql+psycopg', 'postgresql+psycopg2')
                or parsed.database != 'pruvs_business_staging'):
            raise RuntimeError('Combined staging requires isolated pruvs_business_staging database')
        normalized = parsed.set(drivername='postgresql+psycopg').render_as_string(hide_password=False)
        settings = Settings(database_url=normalized)
    else:
        settings = Settings()
    settings.validate_runtime()
    return settings
