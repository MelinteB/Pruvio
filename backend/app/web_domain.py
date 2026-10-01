"""Move browser page visits to the configured domain without redirecting APIs."""
import os
import re
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import RedirectResponse


_PAGES = {"/", "/register", "/account", "/upload", "/history", "/support",
          "/terms", "/privacy", "/reset-password"}
_PAGE_PATTERNS = (
    r"/receipt/[0-9]+",
    r"/s/[^/]+",
    r"/split-bill/cases/[0-9]+/widget-ui",
    r"/split-bill/sessions/[^/]+/(?:join|widget-ui)",
    r"/split-bill/sessions/[^/]+/p/[^/]+/widget-ui",
)


def canonical_browser_redirect(request: Request) -> RedirectResponse | None:
    if os.getenv("CANONICAL_REDIRECT_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    if request.method not in {"GET", "HEAD"}:
        return None
    path = request.url.path
    if path not in _PAGES and not any(re.fullmatch(pattern, path) for pattern in _PAGE_PATTERNS):
        return None
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    target = urlsplit(base)
    # Only a complete HTTPS origin may be used as the configured destination.
    if (target.scheme != "https" or not target.hostname or target.username or target.password
            or target.path or target.query or target.fragment):
        return None
    if request.url.hostname == target.hostname and (request.url.port or 443) == (target.port or 443):
        return None
    destination = base + path
    if request.url.query:
        destination += "?" + request.url.query
    return RedirectResponse(destination, status_code=307, headers={"Cache-Control": "no-store"})
