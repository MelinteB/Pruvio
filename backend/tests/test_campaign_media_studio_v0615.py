"""Campaign media workflow regression: no live network or database required."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from business import pilot_v05, media_v067
from business.ai_campaign_artwork_v0611 import ai_readiness
from business.db import Base
from business.models import Merchant, Program, Promotion, Store


@pytest.fixture
def campaign_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Merchant(id="merchant1", name="Bistro Central"),
            Store(id="store1", merchant_id="merchant1", name="Bistro Central",
                  address="Bucharest", latitude=44.4, longitude=26.1),
            Program(id="program1", merchant_id="merchant1", store_id="store1",
                    title="Breakfast rewards", min_purchase_minor=2000,
                    stamps_required=2, reward_minor=1000, currency="RON", status="published"),
            Promotion(id="promo1", merchant_id="merchant1", program_id="program1",
                      headline="Existing title", message="Existing message", status="draft"),
        ])
        db.commit()
        yield db
    engine.dispose()


def payload(**overrides):
    args = dict(
        program_id="program1", headline="Fresh breakfast promotion",
        message="Enjoy a reward after qualifying merchant-verified purchases.",
        duration_days=20,
    )
    args.update(overrides)
    return pilot_v05.PromotionIn(**args)


def test_draft_update_scoped_and_preserves_program_conditions(campaign_db):
    db = campaign_db
    staff = SimpleNamespace(role="owner", merchant_id="merchant1")
    result = pilot_v05.update_promotion_draft("promo1", payload(), staff, db)
    assert result["headline"] == "Fresh breakfast promotion"
    assert result["duration_days"] == 20
    assert result["reward_minor"] == 1000
    assert result["min_purchase_minor"] == 2000
    assert result["stamps_required"] == 2
    assert result["status"] == "draft"
    assert db.get(Promotion,"promo1").headline == "Fresh breakfast promotion"


def test_published_promotion_cannot_be_edited(campaign_db):
    db = campaign_db
    db.get(Promotion,"promo1").status="published"
    db.commit()
    with pytest.raises(HTTPException) as error:
        pilot_v05.update_promotion_draft(
            "promo1", payload(), SimpleNamespace(role="owner", merchant_id="merchant1"), db
        )
    assert error.value.status_code == 409
    assert db.get(Promotion,"promo1").headline == "Existing title"


def test_other_merchant_cannot_edit_draft(campaign_db):
    db = campaign_db
    with pytest.raises(HTTPException) as error:
        pilot_v05.update_promotion_draft(
            "promo1", payload(), SimpleNamespace(role="owner", merchant_id="other"), db
        )
    assert error.value.status_code == 404
    assert db.get(Promotion,"promo1").headline == "Existing title"


def test_campaign_media_requires_approved_host(monkeypatch):
    monkeypatch.setenv("PRUVS_CAMPAIGN_MEDIA_HOSTS", "media.pruvs.io")
    unapproved = payload(media_url="https://example.org/assets/a.jpg", media_type="image/jpeg")
    with pytest.raises(HTTPException) as error:
        pilot_v05.campaign_media(unapproved)
    assert error.value.status_code == 422


def test_config_invalid_or_missing_is_rejected(monkeypatch):
    for key in (
        "PRUVS_CAMPAIGN_R2_ENDPOINT_URL", "PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID",
        "PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY", "PRUVS_CAMPAIGN_R2_BUCKET",
        "PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL", "PRUVS_CAMPAIGN_MEDIA_HOSTS"
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(HTTPException) as error:
        media_v067.bucket_config()
    assert error.value.status_code == 503


def test_config_accepts_valid_https_public_host(monkeypatch):
    settings = {
        "PRUVS_CAMPAIGN_R2_ENDPOINT_URL": "https://example-id.r2.cloudflarestorage.com",
        "PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID": "test-only-id",
        "PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY": "test-only-secret",
        "PRUVS_CAMPAIGN_R2_BUCKET": "pruvs-campaigns-test",
        "PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL": "https://media.pruvs.io",
        "PRUVS_CAMPAIGN_MEDIA_HOSTS": "media.pruvs.io",
    }
    for k, v in settings.items():
        monkeypatch.setenv(k, v)
    assert media_v067.bucket_config()["PRUVS_CAMPAIGN_R2_BUCKET"] == "pruvs-campaigns-test"


def test_frontend_keeps_media_server_generated():
    source = (Path(__file__).resolve().parents[1] / "business_frontend" / "src" / "PromotionConsole.jsx").read_text(encoding="utf-8")
    assert "Campaign asset HTTPS URL" not in source
    assert "setMediaUrl(data.media_url)" in source
    assert "Local preview only" in source
    assert "mediaCannotSave" in source
    library = (Path(__file__).resolve().parents[1] / "business_frontend" / "src" / "CampaignLibrary.jsx").read_text(encoding="utf-8")
    assert "Duplicate" in library
    assert "Edit before publishing" in library


def test_diagnostics_list_missing_setting_names_without_secrets(monkeypatch):
    for key in media_v067.CAMPAIGN_STORAGE_KEYS:
        monkeypatch.delenv(key, raising=False)
    report = media_v067.media_configuration_diagnostics()
    assert report['issue'] == 'missing_settings'
    assert set(report['missing_settings']) == set(media_v067.CAMPAIGN_STORAGE_KEYS)
    assert 'values' not in report


def test_diagnostics_reports_host_mismatch_without_leaking_urls(monkeypatch):
    for key, value in {
        'PRUVS_CAMPAIGN_R2_ENDPOINT_URL': 'https://sample.r2.cloudflarestorage.com',
        'PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID': 'dummy-id',
        'PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY': 'DO-NOT-PRINT-SECRET',
        'PRUVS_CAMPAIGN_R2_BUCKET': 'public-demo',
        'PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL': 'https://pub-example.r2.dev',
        'PRUVS_CAMPAIGN_MEDIA_HOSTS': 'https://pub-example.r2.dev',
    }.items():
        monkeypatch.setenv(key, value)
    report = media_v067.media_configuration_diagnostics()
    assert report['issue'] == 'public_hostname_not_allowlisted'
    assert report['missing_settings'] == []
    assert 'DO-NOT-PRINT-SECRET' not in str(report)
    assert 'pub-example' not in str(report)


def test_diagnostics_accept_valid_hostname(monkeypatch):
    for key, value in {
        'PRUVS_CAMPAIGN_R2_ENDPOINT_URL': 'https://sample.r2.cloudflarestorage.com',
        'PRUVS_CAMPAIGN_R2_ACCESS_KEY_ID': 'dummy-id',
        'PRUVS_CAMPAIGN_R2_SECRET_ACCESS_KEY': 'dummy-secret',
        'PRUVS_CAMPAIGN_R2_BUCKET': 'public-demo',
        'PRUVS_CAMPAIGN_MEDIA_PUBLIC_BASE_URL': 'https://pub-example.r2.dev',
        'PRUVS_CAMPAIGN_MEDIA_HOSTS': 'pub-example.r2.dev',
    }.items():
        monkeypatch.setenv(key, value)
    report = media_v067.media_configuration_diagnostics()
    assert report == {'ready': True, 'issue': None, 'missing_settings': []}
