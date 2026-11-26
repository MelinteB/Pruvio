"""Verify that the React build matches the source files and backend release."""
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "frontend"
try:
    manifest = json.loads((root / "dist/build-manifest.json").read_text(encoding="utf-8"))
    release_source = (root.parent / "app/reliability.py").read_text(encoding="utf-8")
    version = re.search(r'^RELEASE = "([0-9]+\.[0-9]+\.[0-9]+)"$', release_source, re.M)
    if not version or manifest.get("version") != version.group(1):
        raise ValueError("Build manifest release differs from the backend release.")
    for kind in ("source", "assets"):
        for relative, wanted in manifest[kind].items():
            file = (root / relative).resolve()
            if not file.is_relative_to(root.resolve()):
                raise ValueError("Invalid build path")
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != wanted:
                raise ValueError(f"React build is stale or missing: {relative}. Run npm ci && npm run build in backend/frontend.")
    print("Pruvs React production build verified.")
except (OSError, KeyError, ValueError, TypeError) as e:
    print(f"BUILD CHECK FAILED: {e}", file=sys.stderr)
    sys.exit(1)
