#!/usr/bin/env python3
"""Pruvs 7.1.37 release gate: read-only checks, scoped Git staging, live fingerprint.

No dependencies other than Python 3.11+ standard library. No secrets or user
records are loaded or printed. Never commits, pushes, deploys or migrates a DB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

EXPECTED_RELEASE = '7.1.37'
START_RELEASE = (7, 1, 22)
ASSET_LIMIT = 3_000_000
RELEASE_DIR_RE = re.compile(r'^pruvs_v(7_1_\d+)(?:_|$)')
SENSITIVE_CONTENT = re.compile(r'(?:sk_live_[A-Za-z0-9]{12,}|rk_live_[A-Za-z0-9]{12,}|whsec_[A-Za-z0-9]{12,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)', re.I)


class GateError(RuntimeError):
    pass


def root_path(value: str | Path) -> Path:
    root = Path(value).resolve()
    if not (root / 'backend/app/main.py').is_file() or not (root / 'backend/frontend/package.json').is_file():
        raise GateError('--project must be the Pruvs Git root, containing backend/app/main.py and backend/frontend/package.json')
    return root


def resolved_command(args, *, windows=None, which=None):
    """Locate Windows npm.cmd and retain the current Python virtualenv."""
    if windows is None:
        windows = os.name == 'nt'
    if which is None:
        which = shutil.which
    command = list(args)
    if command and command[0] == 'python':
        command[0] = sys.executable
    elif command and command[0] == 'npm' and windows:
        command[0] = which('npm.cmd') or which('npm') or 'npm.cmd'
    return command


def invoke(args, cwd: Path, *, capture=True):
    args = resolved_command(args)
    try:
        return subprocess.run(args, cwd=cwd, text=True, encoding='utf-8', errors='replace',
                              stdout=subprocess.PIPE if capture else None,
                              stderr=subprocess.PIPE if capture else None, check=False)
    except FileNotFoundError:
        raise GateError(f'Required command not available: {args[0]}') from None


def git(root: Path, *args: str, check=True) -> str:
    process = invoke(['git', *args], root)
    if check and process.returncode:
        # Do not print raw stderr here; Git remote names/URLs may contain credentials.
        raise GateError(f'git {args[0]} failed (exit {process.returncode}); inspect Git configuration.')
    return process.stdout.strip()


def version(root: Path) -> str | None:
    path = root / 'backend/app/reliability.py'
    match = re.search(r'^RELEASE\s*=\s*[\'"](\d+\.\d+\.\d+)[\'"]', path.read_text(encoding='utf-8'), re.M)
    return match.group(1) if match else None


def backend_report(root: Path, *, strict_hashes=True) -> dict:
    # Source module deliberately imports Python stdlib only.
    sys.path.insert(0, str(root / 'backend'))
    try:
        from app.reliability import frontend_build_report
    finally:
        sys.path.remove(str(root / 'backend'))
    return frontend_build_report(root / 'backend/frontend/dist', verify_hashes=strict_hashes)


def checksum(path: Path, *, normalize=False) -> str | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    if normalize:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def source_integrity(root: Path) -> list[str]:
    manifest_path = root / 'backend/frontend/dist/build-manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        sources = manifest['source']
        if not isinstance(sources, dict) or not sources:
            raise ValueError('Invalid source map')
    except (OSError, ValueError, KeyError, TypeError):
        return ['missing_or_invalid_source_manifest']
    failures = []
    frontend = root / 'backend/frontend'
    for rel, hash_value in sources.items():
        if not isinstance(rel, str) or not isinstance(hash_value, str) or not re.fullmatch(r'[a-f0-9]{64}', hash_value):
            failures.append('invalid_source_manifest_entry')
            continue
        candidate = PurePosixPath(rel)
        if candidate.is_absolute() or '..' in candidate.parts or not candidate.parts:
            failures.append('unsafe_source_path')
            continue
        target = frontend.joinpath(*candidate.parts)
        if not target.resolve().is_relative_to(frontend.resolve()) or checksum(target) != hash_value:
            failures.append('source_changed_since_build:' + rel)
    return sorted(set(failures))


def preflight(root: Path, expected: str = EXPECTED_RELEASE) -> list[tuple[str, str]]:
    findings = []
    current = version(root)
    if current != expected:
        findings.append(('BLOCK', f'Backend version {current or "unknown"}; expected {expected}'))
    else:
        findings.append(('OK', f'Backend version {current}'))
    try:
        report = backend_report(root)
        if report['status'] != 'ready' or report.get('version') != expected:
            findings.append(('BLOCK', 'Frontend build unavailable, stale or inconsistent: ' + ','.join(report['checks'])))
        else:
            findings.append(('OK', f'Built assets match {expected}; build ID {report["build_id"]}'))
    except (ImportError, OSError, ValueError, KeyError) as exc:
        findings.append(('BLOCK', f'Cannot inspect frontend build: {type(exc).__name__}'))
    bad_sources = source_integrity(root)
    if bad_sources:
        findings.append(('BLOCK', f'Source/build mismatch ({len(bad_sources)}): ' + ', '.join(bad_sources[:4])))
    else:
        findings.append(('OK', 'All stamped frontend source checksums match'))
    privacy = root / 'backend/app/legal_content.py'
    if not privacy.is_file():
        findings.append(('LAUNCH-BLOCKER', 'Legal/privacy module is missing; production privacy terms not verified.'))
    elif any(token in privacy.read_text(encoding='utf-8') for token in (
        'This prototype does not yet define final retention periods', '[INSERT', 'TBD', 'TODO')):
        findings.append(('LAUNCH-BLOCKER', 'Legal/retention content has known unfinished placeholders; not approved for public launch.'))
    findings.append(('MANUAL', 'Verify production PostgreSQL backup and isolated restore before migrations.'))
    findings.append(('MANUAL', 'Verify account deletion, receipt storage, cross-user access and Stripe live-mode if charging.'))
    return findings


def show_findings(findings: list[tuple[str, str]]) -> int:
    for level, description in findings:
        print(f'[{level}] {description}')
    # LAUNCH-BLOCKER concerns public launch; code can still be staged for a controlled beta.
    return 2 if any(level == 'BLOCK' for level, _ in findings) else 0


def doctor(root: Path) -> int:
    print('Pruvs Launch Control — read-only local diagnosis')
    print('Project:', root)
    print('Local release:', version(root) or 'not found')
    branch = git(root, 'branch', '--show-current')
    head = git(root, 'rev-parse', '--short=12', 'HEAD')
    print('Git branch:', branch or '(detached)')
    print('Git HEAD:', head)
    upstream = invoke(['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'], root)
    print('Upstream:', upstream.stdout.strip() if upstream.returncode == 0 else 'unconfigured')
    if upstream.returncode == 0:
        ahead = git(root, 'rev-list', '--count', '@{upstream}..HEAD')
        behind = git(root, 'rev-list', '--count', 'HEAD..@{upstream}')
        print('Commits ahead/behind cached upstream:', ahead, '/', behind, '(fetch separately to refresh)')
    staged = git(root, 'diff', '--cached', '--name-only', '-z')
    print('Files staged:', len([x for x in staged.split('\0') if x]))
    git_status = git(root, 'status', '--porcelain', '-uno')
    print('Tracked working-tree changes:', len([x for x in git_status.splitlines() if x]))
    print('Untracked backup and installer files are not staged by Launch Control.')
    return show_findings(preflight(root))


def releases_to_stage(root: Path, since: str, target: str) -> tuple[list[str], dict[str, dict]]:
    try:
        floor, ceiling = tuple(int(n) for n in since.split('.')), tuple(int(n) for n in target.split('.'))
    except ValueError:
        raise GateError('Invalid --since/--expected version') from None
    if floor < START_RELEASE or ceiling < floor or ceiling[:2] != (7, 1):
        raise GateError('Supported manifest range begins at v7.1.22 and must end at 7.1.x')
    directory = root / 'updates'
    matches = []
    for folder in directory.iterdir() if directory.is_dir() else []:
        if not folder.is_dir() or folder.is_symlink():
            continue
        match = RELEASE_DIR_RE.match(folder.name)
        if not match or not (folder / 'manifest.json').is_file():
            continue
        value = tuple(int(n) for n in match.group(1).split('_'))
        if floor <= value <= ceiling:
            matches.append((value, folder))
    versions_present = {v for v, _ in matches}
    required = {(7, 1, n) for n in range(floor[2], ceiling[2] + 1)}
    missing = required - versions_present
    if missing:
        raise GateError('Missing extracted release manifests: ' + ', '.join('.'.join(map(str, v)) for v in sorted(missing)))
    paths = set()
    latest_specs = {}
    for _, folder in sorted(matches, key=lambda item: (item[0], item[1].name)):
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest.get('files'), dict) or not manifest['files']:
            raise GateError('Invalid release manifest: ' + folder.name)
        for relative, spec in manifest['files'].items():
            if not isinstance(relative, str) or not isinstance(spec, dict):
                raise GateError('Invalid release manifest entry: ' + folder.name)
            p = PurePosixPath(relative)
            if p.is_absolute() or not p.parts or '..' in p.parts or not (p.parts[0] in ('app', 'frontend', 'tests', 'scripts') or p.parts == ('config', 'retention-policy.example.json')):
                raise GateError('Unsafe release path: ' + relative)
            target_path = root / 'backend' / Path(*p.parts)
            if (not target_path.is_file() or target_path.is_symlink() or
                    not target_path.resolve().is_relative_to((root / 'backend').resolve())):
                raise GateError('Expected release file missing or unsafe: ' + relative)
            paths.add('backend/' + p.as_posix())
            latest_specs[p.as_posix()] = spec
    # Every staged file must match the newest package's expected content, including CRLF normalization.
    for relative, spec in latest_specs.items():
        expected_hash = spec.get('updated_sha256')
        if not expected_hash or checksum(root / 'backend' / relative, normalize=spec.get('text', True)) != expected_hash:
            raise GateError('Release file differs from the last installed package: ' + relative)
    return sorted(paths), latest_specs


def stage(root: Path, since: str, expected: str, apply: bool) -> int:
    print('Launch Control — scoped Git staging' + (' (APPLY)' if apply else ' (PREVIEW ONLY)'))
    findings = preflight(root, expected)
    if show_findings(findings):
        raise GateError('Build or source gate failed; run npm test && npm run build, then retry.')
    paths, _ = releases_to_stage(root, since, expected)
    print(f'Selected {len(paths)} distinct source/test files from release manifests {since}–{expected}.')
    print('Built assets: backend/frontend/dist/ (old hashes removed, new hashes included).')
    print('Excluded: backups, updates/, installer markers, unrelated tracked deletions.')
    if not apply:
        print('PREVIEW: no Git changes made. Re-run with --apply after reviewing the release manifests.')
        return 0
    if git(root, 'branch', '--show-current') != 'main':
        raise GateError('Refusing stage: expected deployment branch main')
    if git(root, 'diff', '--cached', '--name-only'):
        raise GateError('Git index is not empty. Review or commit/unstage existing staged changes first.')
    if not (root / '.git').exists() and invoke(['git', 'rev-parse', '--is-inside-work-tree'], root).returncode:
        raise GateError('Not a Git checkout')
    # Stage exactly the allow-listed files, never the whole repository.
    result = invoke(['git', 'add', '--', *paths], root)
    if result.returncode:
        raise GateError('Cannot stage one or more release files (git add exited nonzero).')
    result = invoke(['git', 'add', '-A', '--', 'backend/frontend/dist/'], root)
    if result.returncode:
        raise GateError('Cannot stage built assets (git add exited nonzero).')
    staged = git(root, 'diff', '--cached', '--name-only', '-z').split('\0')
    allowed = set(paths)
    unexpected = [p for p in staged if p and p not in allowed and not p.startswith('backend/frontend/dist/')]
    if unexpected:
        # Do not undo/alter the index automatically; user can inspect/unstage.
        raise GateError('Staged paths outside allowlist; inspect index: ' + ', '.join(unexpected[:4]))
    diff = git(root, 'diff', '--cached', '--unified=0', '--', *paths)
    if any(SENSITIVE_CONTENT.search(line) for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++')):
        raise GateError('Potential secret string in staged additions; inspect diff, do not push.')
    check = invoke(['git', 'diff', '--cached', '--check'], root)
    if check.returncode:
        raise GateError('git diff --cached --check failed; inspect staged diff.')
    actual = [p for p in staged if p]
    if not actual:
        raise GateError('No staged changes: local release may already be committed. Use doctor/verify-live.')
    print(f'PASS: {len(actual)} paths staged. No unrelated backups or update folders staged.')
    print('NEXT: git diff --cached --name-status; git diff --cached --stat; verify backup; git commit; push the reviewed commit to the deployment branch.')
    return 0


def fetch(base: str, path: str, limit: int = ASSET_LIMIT) -> tuple[bytes, dict]:
    url = base + path
    req = urllib.request.Request(url, headers={
        'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'User-Agent': 'PruvsLaunchControl/7.1.37'})
    with urllib.request.urlopen(req, timeout=15) as response:
        if response.status != 200:
            raise GateError(f'Remote endpoint {path} returned HTTP {response.status}')
        final = urllib.parse.urlparse(response.url)
        origin = urllib.parse.urlparse(base)
        if (final.scheme, final.netloc) != (origin.scheme, origin.netloc):
            raise GateError('Remote redirect changed the origin; refusing to inspect a different site')
        payload = response.read(limit + 1)
        if len(payload) > limit:
            raise GateError('Response too large: ' + path)
        return payload, dict(response.headers.items())


def live(root: Path, base: str, *, fetcher=fetch) -> int:
    parsed = urllib.parse.urlparse(base)
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))) or not parsed.netloc or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
        raise GateError('--url must be a plain HTTPS origin (HTTP only for localhost)')
    base = base.rstrip('/')
    report = backend_report(root, strict_hashes=True)
    if report['status'] != 'ready':
        raise GateError('Local bundle is not ready. Rebuild before comparing production.')
    if source_integrity(root):
        raise GateError('Local source changed after the build; run npm run build again.')
    stamp = '?launch_control=' + str(int(time.time()))
    try:
        remote_bytes, _ = fetcher(base, '/api/v1/release' + stamp)
        remote = json.loads(remote_bytes)
        print(f'Local release {report["version"]}, build {report["build_id"]}; remote release {remote.get("version")}, build {remote.get("build_id")}')
        if (remote.get('status') != 'ready' or remote.get('version') != report['version'] or remote.get('build_id') != report['build_id'] or remote.get('assets') != report['assets']):
            raise GateError('Live release metadata does not match the built application.')
        ready_bytes, _ = fetcher(base, '/ready' + stamp)
        ready = json.loads(ready_bytes)
        if not isinstance(ready, dict) or ready.get('status') != 'ready':
            raise GateError('Live /ready endpoint is not ready.')
        html_bytes, _ = fetcher(base, '/' + stamp)
        actual_assets = sorted(set(re.findall(rb'["\'](/assets/[A-Za-z0-9_./-]+\.(?:js|css))["\']', html_bytes)))
        actual_assets = [a.decode('ascii') for a in actual_assets]
        if actual_assets != report['assets']:
            raise GateError('Live HTML references different frontend assets; possible stale frontend or CDN cache.')
        manifest = json.loads((root / 'backend/frontend/dist/build-manifest.json').read_text(encoding='utf-8'))
        for path in actual_assets:
            expected_sha = manifest['assets']['dist' + path]
            payload, _ = fetcher(base, path + stamp)
            if hashlib.sha256(payload).hexdigest() != expected_sha:
                raise GateError('Live asset checksum differs: ' + path)
        _, headers = fetcher(base, '/health' + stamp)
        request_id = next((v for k, v in headers.items() if k.lower() == 'x-pruvs-request-id'), '')
        if not re.fullmatch(r'[a-f0-9]{24}', request_id):
            raise GateError('Live request tracing header absent or invalid')
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, UnicodeError) as exc:
        raise GateError('Cannot fully verify live release (' + type(exc).__name__ + ').') from None
    print(f'PASS: live {report["version"]} equals local build {report["build_id"]}; HTML, JS/CSS bytes, readiness and request tracing verified.')
    return 0


def test_and_build(root: Path) -> int:
    backend = root / 'backend'
    frontend = backend / 'frontend'
    commands = [
        (['python', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*v7_1_*.py', '-v'], backend),
        (['npm', 'test'], frontend),
        (['npm', 'run', 'build'], frontend),
    ]
    for command, directory in commands:
        # Use the same Python executable as this script, including the user's venv.
        if command[0] == 'python': command[0] = sys.executable
        print('RUN:', ' '.join(Path(x).name if i == 0 else x for i, x in enumerate(command)), flush=True)
        code = invoke(command, directory, capture=False).returncode
        if code:
            raise GateError('Tests/build failed: ' + command[1] if len(command) > 1 else 'Tests/build failed')
    return show_findings(preflight(root))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'preflight', 'test', 'stage', 'verify-live', 'audit-launch'):
        p = sub.add_parser(name)
        p.add_argument('--project', default='.', help='Pruvs Git checkout root')
        if name in ('preflight', 'stage'):
            p.add_argument('--expected', default=EXPECTED_RELEASE)
        if name == 'stage':
            p.add_argument('--since', default='7.1.22', help='Oldest release whose manifest must be staged')
            p.add_argument('--apply', action='store_true', help='Actually stage allow-listed files; default is preview')
        if name == 'verify-live':
            p.add_argument('--url', default='https://pruvs.io')
        if name == 'audit-launch':
            p.add_argument('--evidence', type=Path, help='Private evidence file outside Git')
            p.add_argument('--retention-policy', type=Path, help='Reviewed retention worksheet')
    args = parser.parse_args(argv)
    try:
        root = root_path(args.project)
        if args.command == 'doctor': return doctor(root)
        if args.command == 'preflight': return show_findings(preflight(root, args.expected))
        if args.command == 'test': return test_and_build(root)
        if args.command == 'stage': return stage(root, args.since, args.expected, args.apply)
        if args.command == 'verify-live': return live(root, args.url)
        if args.command == 'audit-launch':
            command = [sys.executable, str(root / 'backend/scripts/launch_evidence.py'),
                       '--backend', str(root / 'backend'), '--strict']
            if args.evidence: command += ['--evidence', str(args.evidence)]
            if args.retention_policy: command += ['--retention-policy', str(args.retention_policy)]
            return invoke(command, root, capture=False).returncode
    except (GateError, OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print('STOP:', exc, file=sys.stderr)
        return 2
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
