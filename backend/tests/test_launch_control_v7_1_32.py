"""Pruvs 7.1.32 release gate behavior: controlled staging and remote build tests."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import launch_control as gate


def sha(value):
    return hashlib.sha256(value).hexdigest()


class LaunchControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = self.root / 'backend'
        self.frontend = self.backend / 'frontend'
        (self.backend / 'app').mkdir(parents=True)
        (self.frontend / 'src').mkdir(parents=True)
        (self.frontend / 'dist/assets').mkdir(parents=True)
        (self.backend / 'app/main.py').write_text('# fake main\n')
        (self.backend / 'app/reliability.py').write_text('RELEASE = "7.1.32"\n')
        (self.frontend / 'package.json').write_text('{"name":"pruvs"}\n')
        (self.frontend / 'src/main.jsx').write_text('const version = "7.1.32";\n')
        self.build()

    def build(self, javascript=b'console.log("launch")', css=b'body{margin:0}'):
        dist = self.frontend / 'dist'
        (dist / 'index.html').write_text('<script src="/assets/index-CI.js"></script>\n<link href="/assets/index-CI.css" rel="stylesheet">\n')
        (dist / 'assets/index-CI.js').write_bytes(javascript)
        (dist / 'assets/index-CI.css').write_bytes(css)
        manifest = {
            'version': '7.1.32',
            'assets': {'dist/assets/index-CI.js': sha(javascript), 'dist/assets/index-CI.css': sha(css)},
            'source': {'src/main.jsx': gate.checksum(self.frontend / 'src/main.jsx')},
        }
        (dist / 'build-manifest.json').write_text(json.dumps(manifest))

    def git(self, *args):
        proc = subprocess.run(['git', *args], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def setup_git(self):
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Pruvs Tests')
        self.git('add', '--', 'backend/app/main.py', 'backend/app/reliability.py',
                 'backend/frontend/package.json', 'backend/frontend/src/main.jsx', 'backend/frontend/dist/')
        self.git('commit', '-m', 'baseline')

    def manifest(self, version='7.1.32', entries=None):
        folder = self.root / 'updates' / ('pruvs_v' + version.replace('.', '_') + '_launch_control')
        folder.mkdir(parents=True, exist_ok=True)
        entries = entries if entries is not None else {'app/reliability.py': {
            'updated_sha256': gate.checksum(self.backend / 'app/reliability.py', normalize=True), 'text': True}}
        (folder / 'manifest.json').write_text(json.dumps({'version': version, 'files': entries}))
        return folder

    def test_preflight_passes_if_fingerprint_and_sources_match(self):
        findings = gate.preflight(self.root)
        self.assertFalse(any(level == 'BLOCK' for level, _ in findings))

    def test_stale_dist_and_source_changes_fail_closed(self):
        (self.frontend / 'src/main.jsx').write_text('changed')
        self.assertIn('source_changed_since_build:src/main.jsx', gate.source_integrity(self.root))
        self.assertEqual(gate.show_findings(gate.preflight(self.root)), 2)
        self.build()
        (self.frontend / 'dist/assets/index-CI.js').write_text('tampered')
        self.assertEqual(gate.show_findings(gate.preflight(self.root)), 2)

    def test_release_manifest_missing_or_unsafe_path_is_rejected(self):
        with self.assertRaisesRegex(gate.GateError, 'Missing extracted release manifests'):
            gate.releases_to_stage(self.root, '7.1.32', '7.1.32')
        self.manifest(entries={'../outside': {'updated_sha256': '0'*64}})
        with self.assertRaisesRegex(gate.GateError, 'Unsafe release path'):
            gate.releases_to_stage(self.root, '7.1.32', '7.1.32')

    def test_manifest_accepts_crlf_windows_text(self):
        """Release fingerprints must behave the same on Windows and Linux."""
        self.setup_git()
        self.manifest()
        original = self.backend / 'app/reliability.py'
        original.write_bytes(original.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertNotIn(b'\r\r\n', original.read_bytes())
        paths, specs = gate.releases_to_stage(self.root, '7.1.32', '7.1.32')
        self.assertIn('backend/app/reliability.py', paths)
        self.assertTrue(specs['app/reliability.py']['text'])

    def test_manifest_detects_modified_app_source(self):
        self.manifest()
        (self.backend / 'app/reliability.py').write_text('RELEASE="7.1.32"\n# modified')
        with self.assertRaisesRegex(gate.GateError, 'differs from the last installed package'):
            gate.releases_to_stage(self.root, '7.1.32', '7.1.32')

    def test_stage_preview_leaves_index_and_backups_untouched(self):
        self.setup_git()
        self.manifest()
        (self.root / 'pruvs_backup_test.txt').write_text('local backup')
        self.assertEqual(gate.stage(self.root, '7.1.32', '7.1.32', apply=False), 0)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_stage_apply_targets_only_manifest_and_built_assets(self):
        self.setup_git()
        self.manifest()
        (self.backend / 'app/reliability.py').write_text('RELEASE = "7.1.32"\n')  # unchanged
        self.frontend.joinpath('dist/assets/old.js').write_text('old')
        self.git('add', '--', 'backend/frontend/dist/assets/old.js')
        self.git('commit', '-m', 'old asset')
        self.frontend.joinpath('dist/assets/old.js').unlink()
        # New generated asset referenced by manifest after a rebuild
        self.build(javascript=b'console.log("new")')
        (self.root / 'pruvs_backup_secret.env').write_text('do not stage')
        self.assertEqual(gate.stage(self.root, '7.1.32', '7.1.32', apply=True), 0)
        staged = self.git('diff', '--cached', '--name-only').splitlines()
        self.assertTrue(staged)
        self.assertTrue(all(p.startswith('backend/frontend/dist/') or p == 'backend/app/reliability.py' for p in staged))
        self.assertFalse(any('backup' in p for p in staged))

    def test_stage_refuses_preexisting_index_changes(self):
        self.setup_git()
        self.manifest()
        (self.backend / 'app/main.py').write_text('unrelated file')
        self.git('add', '--', 'backend/app/main.py')
        with self.assertRaisesRegex(gate.GateError, 'Git index is not empty'):
            gate.stage(self.root, '7.1.32', '7.1.32', apply=True)

    def test_stage_refuses_wrong_branch(self):
        self.setup_git()
        self.manifest()
        self.git('checkout', '-b', 'work-branch')
        with self.assertRaisesRegex(gate.GateError, 'deployment branch main'):
            gate.stage(self.root, '7.1.32', '7.1.32', apply=True)

    def remote(self, broken=None):
        report = gate.backend_report(self.root)
        manifest = json.loads((self.frontend / 'dist/build-manifest.json').read_text())
        def fetcher(base, path):
            if path.startswith('/api/v1/release'):
                data = {**report}
                if broken == 'metadata': data['build_id'] = 'old-build'
                return json.dumps(data).encode(), {}
            if path.startswith('/ready'):
                return json.dumps({'status':'ready'}).encode(), {}
            if path.startswith('/health'):
                return b'{}', {'X-Pruvs-Request-ID':'a'*24}
            if path.startswith('/?'):
                if broken == 'html': return b'<script src="/assets/old.js"></script>', {}
                return (self.frontend / 'dist/index.html').read_bytes(), {}
            if path.startswith('/assets/'):
                payload = (self.frontend / 'dist' / path.split('?',1)[0].lstrip('/')).read_bytes()
                return (payload + b'changed' if broken == 'asset' else payload), {}
            raise AssertionError(path)
        return fetcher

    def test_live_verifier_confirms_actual_html_and_asset_bytes(self):
        self.assertEqual(gate.live(self.root, 'https://pruvs.io', fetcher=self.remote()), 0)

    def test_live_verifier_fails_on_stale_metadata_or_html_or_asset(self):
        for failure in ('metadata', 'html', 'asset'):
            with self.subTest(failure=failure):
                with self.assertRaises(gate.GateError):
                    gate.live(self.root, 'https://pruvs.io', fetcher=self.remote(failure))

    def test_http_external_and_credentials_are_rejected(self):
        for target in ('http://pruvs.io', 'https://someone:password@pruvs.io', 'https://pruvs.io/other'):
            with self.assertRaisesRegex(gate.GateError, 'HTTPS origin'):
                gate.live(self.root, target, fetcher=self.remote())

    def test_windows_npm_prefers_cmd_launcher(self):
        lookups = []
        def finder(name):
            lookups.append(name)
            return r'C:\Program Files\nodejs\npm.cmd' if name == 'npm.cmd' else None
        self.assertEqual(gate.resolve_executable(['npm', 'test'], windows=True, finder=finder),
                         [r'C:\Program Files\nodejs\npm.cmd', 'test'])
        self.assertEqual(lookups, ['npm.cmd'])

    def test_windows_npm_exe_fallback_and_missing_launcher(self):
        def finder(name):
            return r'C:\node\npm.exe' if name == 'npm.exe' else None
        self.assertEqual(gate.resolve_executable(['npm', 'run', 'build'], windows=True, finder=finder),
                         [r'C:\node\npm.exe', 'run', 'build'])
        with self.assertRaisesRegex(gate.GateError, r'npm\.cmd'):
            gate.resolve_executable(['npm', 'test'], windows=True, finder=lambda _: None)

    def test_unix_and_other_commands_remain_unchanged(self):
        forbid = lambda _: self.fail('which() must not run for these commands')
        for args, win in ((['npm', 'test'], False), (['git', 'status'], True), (['python', '-V'], True)):
            self.assertEqual(gate.resolve_executable(args, windows=win, finder=forbid), args)

    def test_invoke_uses_resolved_launcher_without_shell(self):
        from unittest.mock import Mock
        with patch.object(gate, 'resolve_executable', return_value=['npm.cmd', 'test']) as resolver, \
             patch.object(gate.subprocess, 'run', return_value=Mock(returncode=0)) as runner:
            result = gate.invoke(['npm', 'test'], self.root, capture=False)
        self.assertEqual(result.returncode, 0)
        resolver.assert_called_once_with(['npm', 'test'])
        self.assertEqual(runner.call_args.args[0], ['npm.cmd', 'test'])
        self.assertNotIn('shell', runner.call_args.kwargs)

    def test_filename_safety_checks_do_not_read_client_records(self):
        source = (ROOT / 'scripts/launch_control.py').read_text()
        self.assertNotIn('SELECT * FROM', source)
        self.assertNotIn('git add .', source)
        self.assertNotIn('git push origin main', source)


if __name__ == '__main__':
    unittest.main()
