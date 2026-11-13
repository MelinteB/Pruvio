"""Optional same-origin hosting of the compiled Business UI, without changing API routing.

Staging only: when PRUVS_BUSINESS_SERVE_UI=true, require a complete Vite dist
copied into backend/business/static_ui. Only known public frontend files are served
at the root; all API routes take precedence and private files stay inaccessible.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

PUBLIC_FILES = (
    "merchant-enroll.html",
    "merchant-enroll.css",
    "merchant-enroll.js",
    "merchant-login-entry.css",
    "merchant-login-entry.js",
    "business-favicon.svg",
)
RESERVED = {"v1", "api", "docs", "redoc", "health", "openapi.json", "assets", "_internal", ".well-known"}


def is_safe_spa_path(path: str) -> bool:
    if path == "":
        return True
    parts = path.split("/")
    if len(parts) > 6 or any(not p or p in (".", "..") or p.startswith(".") for p in parts):
        return False
    if parts[0].lower() in RESERVED:
        return False
    return all("." not in p and p.replace("-", "").replace("_", "").isalnum() for p in parts)


def mount_business_ui(app: FastAPI, *, dist_dir: Path | None = None, enabled: bool | None = None) -> bool:
    if enabled is None:
        enabled = os.getenv("PRUVS_BUSINESS_SERVE_UI", "false").strip().lower() == "true"
    if not enabled:
        return False

    dist = Path(dist_dir) if dist_dir is not None else Path(__file__).resolve().parent / "static_ui"
    index = dist / "index.html"
    assets = dist / "assets"
    missing = [f for f in PUBLIC_FILES if not (dist / f).is_file()]
    if not index.is_file() or not assets.is_dir() or not any(assets.glob("*.js")) or missing:
        raise RuntimeError("Pruvs Business UI enabled but static_ui build is incomplete: " + ", ".join(missing))

    app.mount("/assets", StaticFiles(directory=str(assets)), name="pruvs-business-ui-assets")

    def public_handler(filename: str):
        # No exposed query parameter can override the server-chosen filename.
        async def serve_public_file():
            return FileResponse(str(dist / filename), headers={"Cache-Control": "no-store"})
        return serve_public_file

    for filename in PUBLIC_FILES:
        app.add_api_route("/" + filename, public_handler(filename), methods=["GET"], include_in_schema=False)

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_ui(spa_path: str = ""):
        if not is_safe_spa_path(spa_path):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(str(index), media_type="text/html", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return True
