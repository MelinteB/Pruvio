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


def test_combined_staging_validates_full_schema_without_runtime_ddl():
    source = (BACKEND / "app" / "platform_combined.py").read_text(encoding="utf-8")
    core = (BACKEND / "app" / "react_main.py").read_text(encoding="utf-8")
    assert "pruvs_business_staging" in source
    assert "pruvs_core_staging" in source
    assert "CoreBase.metadata.tables" in source
    assert "BusinessBase.metadata.tables" in source
    assert "ix_users_username_key" in source
    assert "MerchantStorePlace.__table__.create(" not in source
    assert 'if os.getenv("PRUVS_PLATFORM_COMBINED_STAGING", "").strip().lower() != "true":' in core
    assert core.index('if os.getenv("PRUVS_PLATFORM_COMBINED_STAGING"') < core.index("Base.metadata.create_all(bind=engine)")


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


def test_business_sidebar_contains_footer_on_short_screens():
    source = (BACKEND/"business_frontend"/"src"/"business-sidebar-account-fix.css").read_text(encoding="utf-8")
    entry = (BACKEND/"business_frontend"/"src"/"main.jsx").read_text(encoding="utf-8")
    assert ".sidebar nav" in source
    assert "overflow-y: auto" in source
    assert "height: 100dvh" in source
    assert ".sidebar-foot" in source
    assert "business-sidebar-account-fix.css" in entry


def test_core_social_login_has_visible_disabled_provider_options_and_apple_flow():
    source = (BACKEND/"frontend"/"src"/"SocialAuthOptions.jsx").read_text(encoding="utf-8")
    core_auth = (BACKEND/"frontend"/"src"/"Auth.jsx").read_text(encoding="utf-8")
    core_account = (BACKEND/"frontend"/"src"/"Account.jsx").read_text(encoding="utf-8")
    social = (BACKEND/"app"/"react_app"/"social_auth.py").read_text(encoding="utf-8")
    ast.parse(social)
    for provider in ("google", "yahoo", "facebook", "tiktok", "apple", "instagram"):
        assert "id:'" + provider + "'" in source
    assert "Setup required" in source
    assert "p.id!=='instagram'" not in source
    assert "Personal Instagram accounts cannot use this method" in source
    assert '"signup": True' in social
    assert "LoginMethodGrid" in core_auth
    assert "PhoneNumberField" in core_auth
    grid = (BACKEND/"frontend"/"src"/"LoginMethodGrid.jsx").read_text(encoding="utf-8")
    assert grid.index("id: 'google'") < grid.index("id: 'linkedin'") < grid.index("id: 'yahoo'")
    assert "google" in social
    assert "SocialAuthOptions" in core_account
    assert 'APPLE_BRIDGE_COOKIE' in social
    assert 'response_mode"] = "form_post"' in social
    assert '@router.post("/{provider}/callback")' in social
    assert "pruvs_social_accounts" not in source  # UI never sees provider subjects
