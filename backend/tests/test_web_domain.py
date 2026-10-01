from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from app.web_domain import canonical_browser_redirect


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pruvs.io")
    monkeypatch.setenv("CANONICAL_REDIRECT_ENABLED", "true")
    app = FastAPI()

    @app.middleware("http")
    async def redirect(request: Request, call_next):
        result = canonical_browser_redirect(request)
        return result if result is not None else await call_next(request)

    @app.api_route("/{path:path}", methods=["GET", "POST", "HEAD"])
    def page(path: str):
        return {"path": path}

    with TestClient(app, base_url="https://pruvio.onrender.com", follow_redirects=False) as api:
        yield api


def test_shared_link_preserves_token_and_query(client):
    response = client.get("/split-bill/sessions/bill-token/p/person-token/widget-ui?lang=ro")
    assert response.status_code == 307
    assert response.headers["location"] == "https://pruvs.io/split-bill/sessions/bill-token/p/person-token/widget-ui?lang=ro"
    assert response.headers["cache-control"] == "no-store"


def test_new_domain_does_not_loop(client):
    assert client.get("https://pruvs.io/account").status_code == 200


def test_api_upload_and_health_requests_stay_on_original_host(client):
    for path in ("/health", "/static/pruvs-logo.png", "/auth/device/remember", "/webhook/whatsapp", "/split-bill/sessions/token"):
        assert client.get(path).status_code == 200
    assert client.post("/upload", content=b"file contents").status_code == 200
    assert client.post("/auth/device/remember", json={"claim": "test"}).status_code == 200


def test_cutover_can_be_disabled_for_deployment_and_local_testing(client, monkeypatch):
    monkeypatch.setenv("CANONICAL_REDIRECT_ENABLED", "false")
    assert client.get("/register").status_code == 200


def test_only_configured_origin_controls_redirect(client):
    response = client.get("/s/bill-token?next=https://unrelated.example/", headers={"x-forwarded-host": "unrelated.example"})
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://pruvs.io/s/bill-token?")


@pytest.mark.parametrize("origin", ["http://pruvs.io", "https://pruvs.io/path", "https://user@pruvs.io", "", "https://pruvs.io?redirect=elsewhere"])
def test_invalid_canonical_origin_does_not_redirect(client, monkeypatch, origin):
    monkeypatch.setenv("PUBLIC_BASE_URL", origin)
    assert client.get("/account").status_code == 200
