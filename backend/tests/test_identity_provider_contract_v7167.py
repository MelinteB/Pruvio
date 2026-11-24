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

@pytest.mark.parametrize("status,payload,reason", [
    (401, {"error": "invalid_client", "error_description": "private-token"}, "invalid_client"),
    (400, {"error": {"code": 190, "message": "private-token"}}, "190"),
    (200, {"error": {"code": "scope_not_authorized", "message": "private-token"}}, "scope_not_authorized"),
    (400, {"error": "private-token"}, "unclassified_provider_error"),
])
def test_provider_failure_has_safe_diagnostics(monkeypatch, caplog, status, payload, reason):
    import httpx
    from fastapi import HTTPException
    response = httpx.Response(status, json=payload)
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, *args, **kwargs): return response
    monkeypatch.setattr(social.httpx, "Client", Client)
    with pytest.raises(HTTPException) as error:
        social._fetch(social.TOKEN["tiktok"], method="POST", data={"code": "private-code"})
    assert error.value.status_code == 502
    assert "endpoint=tiktok:token" in caplog.text
    assert "reason=" + reason in caplog.text
    assert "private-token" not in caplog.text
    assert "private-code" not in caplog.text


def test_tiktok_success_error_envelope(monkeypatch):
    import httpx
    payload = {"data": {"user": {"open_id": "expected"}}, "error": {"code": "ok"}}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, *args, **kwargs): return httpx.Response(200, json=payload)
    monkeypatch.setattr(social.httpx, "Client", Client)
    assert social._fetch("https://open.tiktokapis.com/v2/user/info/") == payload


def test_yahoo_uses_basic_client_auth(monkeypatch):
    calls = []
    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return {"access_token": "test-access"} if len(calls) == 1 else {"sub": "expected"}
    monkeypatch.setattr(social, "_fetch", fetch)
    monkeypatch.setattr(social, "_oidc_identity", lambda *args: {
        "subject": "expected", "name": "Test", "email": "", "verified": False})
    assert social._oauth_identity("yahoo", "code", "client", "secret",
        "https://example.test/callback", {"nonce": "test"})["subject"] == "expected"
    assert calls[0][1]["auth"] == ("client", "secret")
    assert "client_secret" not in calls[0][1]["data"]
    assert "client_id" not in calls[0][1]["data"]


@pytest.mark.parametrize("provider", ["google", "linkedin", "yahoo", "facebook", "tiktok"])
def test_callback_provider_failure_redirects_without_authenticating(monkeypatch, provider):
    import time
    from types import SimpleNamespace
    from fastapi import HTTPException
    monkeypatch.setenv("PRUVS_SOCIAL_AUTH_STATE_SECRET", "x" * 40)
    monkeypatch.setattr(social, "_ensure_provider", lambda p: None)
    monkeypatch.setattr(social, "_schema_ready", lambda db: None)
    monkeypatch.setattr(social, "_client", lambda p: ("id", "secret", True))
    def fail(*args):
        raise HTTPException(502, "private-token")
    monkeypatch.setattr(social, "_oauth_identity", fail)
    monkeypatch.setattr(social, "_finish_verified_identity",
                        lambda *args: pytest.fail("Must not authenticate"))
    ticket = social._seal({"iat": int(time.time()), "state": "state",
                          "provider": provider, "mode": "login", "next": "/bills"})
    request = SimpleNamespace(method="GET", cookies={social.STATE_COOKIE: ticket})
    response = social.callback(provider, request, code="test-code", state="state", db=None)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?social_error=retry&next=%2Fbills"
    assert response.headers["cache-control"] == "no-store"
    assert "private-token" not in response.headers["location"]
    assert social.STATE_COOKIE in response.headers["set-cookie"]
    with pytest.raises(HTTPException) as invalid_state:
        social.callback(provider, request, code="test-code", state="wrong", db=None)
    assert invalid_state.value.status_code == 400

