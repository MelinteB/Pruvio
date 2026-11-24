"""Draft v7.1.67 provider registry and environment contract."""
import pytest
from app.react_app import social_auth as social

@pytest.mark.parametrize("provider", ["google", "linkedin", "yahoo", "facebook", "tiktok"])
def test_short_provider_keys_and_opt_in(monkeypatch, provider):
    prefix = provider.upper()
    id_key = prefix + ("_CLIENT_KEY" if provider == "tiktok" else "_CLIENT_ID")
    monkeypatch.setenv(id_key, "test-client")
    monkeypatch.setenv(prefix + "_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(prefix + "_ENABLED", "false")
    assert not social._configured(provider)
    monkeypatch.setenv(prefix + "_ENABLED", "true")
    assert social._configured(provider)
    monkeypatch.delenv(prefix + "_CLIENT_SECRET")
    assert not social._configured(provider)

@pytest.mark.parametrize("provider", ["instagram", "apple"])
def test_excluded_providers_fail_closed(monkeypatch, provider):
    prefix = provider.upper()
    monkeypatch.setenv(prefix + "_CLIENT_ID", "test-client")
    monkeypatch.setenv(prefix + "_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(prefix + "_ENABLED", "true")
    assert not social._configured(provider)

def test_linkedin_oidc_metadata():
    assert social.ISSUER["linkedin"] == ("https://www.linkedin.com",)
    assert social.JWKS["linkedin"] == "https://www.linkedin.com/oauth/openid/jwks"
    assert set(social.SCOPES["linkedin"].split()) == {"openid", "profile", "email"}

def test_tiktok_subject_mismatch_rejected(monkeypatch):
    from fastapi import HTTPException
    responses = iter([{"access_token":"fake","open_id":"expected"},
                      {"data":{"user":{"open_id":"other"}}}])
    monkeypatch.setattr(social, "_fetch", lambda *a, **k: next(responses))
    with pytest.raises(HTTPException):
        social._oauth_identity("tiktok", "code", "id", "secret", "https://example.test/callback", {})
