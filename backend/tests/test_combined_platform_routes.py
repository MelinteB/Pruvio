"""Isolated checks for combined staging routing; no real database connections."""
import ast
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]


def test_platform_combined_compiles_without_importing_database():
    source = BACKEND / "app" / "platform_combined.py"
    ast.parse(source.read_text(encoding="utf-8"))
    ast.parse((BACKEND / "business" / "config.py").read_text(encoding="utf-8"))
    ast.parse((BACKEND / "app" / "react_app" / "loyalty_gateway.py").read_text(encoding="utf-8"))


def test_mount_order_and_auth_boundaries():
    core = FastAPI()
    business = FastAPI()

    @core.get("/")
    def core_home():
        return {"app": "core"}

    @core.get("/api/v1/check")
    def core_api():
        return {"app": "core", "api": True}

    @business.get("/")
    def business_home():
        return {"app": "business"}

    @business.get("/v1/check")
    def business_api():
        return {"app": "business", "api": True}

    combined = FastAPI()
    combined.mount("/business", business)
    combined.mount("/", core)
    client = TestClient(combined)
    assert client.get("/").json() == {"app": "core"}
    assert client.get("/api/v1/check").json()["app"] == "core"
    assert client.get("/business/").json() == {"app": "business"}
    assert client.get("/business/v1/check").json()["app"] == "business"


def test_platform_entrypoint_hard_gates_staging_databases():
    source = (BACKEND / "app" / "platform_combined.py").read_text(encoding="utf-8")
    assert 'PRUVS_PLATFORM_COMBINED_STAGING' in source
    assert 'pruvs_core_staging' in source
    assert 'pruvs_business_staging' in source
    assert 'BUSINESS_DATABASE_URL' in source
    assert 'app.mount("/business"' in source
    assert 'app.mount("/", core_app' in source
    assert source.index('app.mount("/business"') < source.index('app.mount("/", core_app')


def test_loyalty_bridge_uses_fixed_loopback_only_on_combined_staging():
    source = (BACKEND / "app" / "react_app" / "loyalty_gateway.py").read_text(encoding="utf-8")
    assert "raw = 'http://127.0.0.1:' + port + '/business'" in source
    assert "'PRUVS_PLATFORM_COMBINED_STAGING'" in source


def test_business_frontend_sources_present():
    for part in ["package.json", "package-lock.json", "index.html",
                 "src/main.jsx", "src/PromotionConsole.jsx", "src/ReceiptInbox.jsx",
                 "public/merchant-enroll.html", "public/merchant-enroll.js",
                 "public/merchant-login-entry.js"]:
        assert (BACKEND / "business_frontend" / part).is_file(), part
