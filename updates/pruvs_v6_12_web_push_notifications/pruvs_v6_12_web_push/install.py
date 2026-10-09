#!/usr/bin/env python3
"""Guarded, idempotent v6.11.1 -> v6.12 update. Standard library only."""
import argparse
import ast
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def backend_at(value):
    path = Path(value).expanduser().resolve()
    if (path / 'app/main.py').is_file():
        return path
    if (path / 'backend/app/main.py').is_file():
        return path / 'backend'
    raise ValueError(f'No app/main.py found in {path} or its backend folder. Pass your existing backend path.')


def prepare(backend):
    edits = json.loads((ROOT / 'edits.json').read_text(encoding='utf-8'))
    outputs = {}
    main = (backend / 'app/main.py').read_text(encoding='utf-8-sig')
    if '6.11.1' not in main and '6.12.0' not in main:
        raise ValueError('Install v6.11 and v6.11.1 first. This package requires v6.11.1.')
    for change in edits:
        path = backend / change['path']
        text = outputs.get(path)
        if text is None:
            text = path.read_text(encoding='utf-8-sig')
        old, new = change['old'], change['new']
        if new in text:
            continue
        if text.count(old) != 1:
            raise ValueError(f'Compatibility check failed: {change["path"]}. Expected code differs. No files changed. Provide this current file for an adapted patch.')
        outputs[path] = text.replace(old, new, 1)
    for source in sorted((ROOT / 'backend').rglob('*')):
        if not source.is_file() or '__pycache__' in source.parts:
            continue
        target = backend / source.relative_to(ROOT / 'backend')
        value = source.read_text(encoding='utf-8')
        if target.exists() and target.read_text(encoding='utf-8-sig') != value:
            raise ValueError(f'New file already exists with different content: {target}. No files changed.')
        outputs[target] = value
    requirements = backend / 'requirements.txt'
    text = requirements.read_text(encoding='utf-8-sig')
    if not any(line.strip().lower().startswith('pywebpush') for line in text.splitlines()):
        outputs[requirements] = text.rstrip() + '\npywebpush>=2.0,<3.0\n'
    for path, value in outputs.items():
        if path.suffix == '.py':
            ast.parse(value, filename=str(path))
    return {path: value for path, value in outputs.items()
            if not path.exists() or path.read_text(encoding='utf-8-sig') != value}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        backend = backend_at(args.backend)
        files = prepare(backend)
    except (ValueError, OSError, SyntaxError) as exc:
        parser.exit(1, f'{exc}\n')
    print(f'Backend: {backend}\nCompatibility check passed. {len(files)} files to update.')
    if args.check or not files:
        return
    backup = backend / 'update_backups' / ('pruvs_v6_12_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True)
    created = []
    changed = []
    try:
        for path, value in files.items():
            relative = path.relative_to(backend)
            if path.exists():
                target = backup / relative; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            else:
                created.append(str(relative))
            changed.append(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding='utf-8', newline='\n')
    except Exception:
        for path in changed:
            saved = backup / path.relative_to(backend)
            if saved.exists(): shutil.copy2(saved, path)
            elif path.exists(): path.unlink()
        raise
    (backup / 'created-files.json').write_text(json.dumps(created, indent=2))
    print(f'Update installed. Backup: {backup}\nInstall dependencies, configure VAPID, then deploy. See README.md.')


if __name__ == '__main__':
    main()
