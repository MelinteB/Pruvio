"""v7.1.37: read-only go-live evidence inventory; no claims of legal approval."""
from __future__ import annotations

from datetime import date, timedelta
import contextlib
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from launch_evidence import (EVIDENCE_ITEMS, _recorded, audit, evidence_state,
                             legal_source_state, retention_state, main)
from retention_review import CATEGORIES


class LaunchEvidenceTests(unittest.TestCase):
    TODAY = date(2026, 10, 30)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = self.root / 'backend'
        (self.backend / 'app').mkdir(parents=True)
        (self.backend / 'app/main.py').write_text('# isolated test fixture\n', encoding='utf-8')
        (self.backend / 'config').mkdir()
        self.policy = self.backend / 'config/retention-policy.example.json'
        self.policy.write_text(json.dumps({'categories': {n: {
            'purpose': None, 'lawful_basis': None, 'retention_rule': None,
            'deletion_method': None, 'reviewer_approval': None,
        } for n in CATEGORIES}}), encoding='utf-8')
        self.evidence = self.root / 'evidence-private.json'
        self.legal = self.backend / 'app/legal_content.py'
        self.legal.write_text('TERMS_TITLE = "Pruvs Terms of Use — Draft"\n', encoding='utf-8')

    def full_policy(self):
        entries = {n: {k: 'Reviewed decision recorded externally' for k in
                 ('purpose','lawful_basis','retention_rule','deletion_method','reviewer_approval')}
                 for n in CATEGORIES}
        self.policy.write_text(json.dumps({'categories': entries}), encoding='utf-8')

    def full_evidence(self, reviewed='2026-10-29'):
        entries = {n: {'decision': 'verified', 'reference': f'ticket:{n}',
                       'reviewer_role': 'Reviewer', 'reviewed_at': reviewed} for n in EVIDENCE_ITEMS}
        self.evidence.write_text(json.dumps({'schema_version': 1, 'evidence': entries}), encoding='utf-8')
        return entries

    def test_missing_private_evidence_is_blocking(self):
        result=audit(self.backend, today=self.TODAY)
        self.assertEqual(result['status'],'incomplete')
        self.assertFalse(result['evidence']['present'])
        self.assertEqual(len(result['evidence']['missing_or_incomplete']),10)

    def test_unapproved_retention_worksheet_is_incomplete(self):
        self.assertEqual(retention_state(self.policy)['incomplete'],12)

    def test_missing_retention_worksheet_fails_closed(self):
        self.policy.unlink()
        self.assertEqual(retention_state(self.policy)['status'],'worksheet_missing_or_invalid')

    def test_malformed_retention_policy_fails_closed(self):
        self.policy.write_text('[not json', encoding='utf-8')
        self.assertEqual(retention_state(self.policy)['status'],'worksheet_missing_or_invalid')

    def test_legal_draft_is_a_blocker_even_with_complete_records(self):
        self.full_policy();self.full_evidence()
        result=audit(self.backend, retention_policy=self.policy,evidence_file=self.evidence,today=self.TODAY)
        self.assertEqual(result['legal_text'],'draft_content')
        self.assertEqual(result['status'],'incomplete')

    def test_missing_legal_file_is_a_blocker(self):
        self.legal.unlink()
        self.assertEqual(legal_source_state(self.legal),'source_missing')

    def test_legal_text_without_markers_requires_independent_approval(self):
        self.legal.write_text('TERMS_TITLE = "Terms of Use"\nPRIVACY_TITLE = "Privacy Notice"\n')
        self.full_policy();self.full_evidence()
        result=audit(self.backend,retention_policy=self.policy,evidence_file=self.evidence,today=self.TODAY)
        self.assertEqual(result['status'],'evidence_recorded_pending_independent_validation')
        self.assertFalse(result['approval_granted'])
        self.assertFalse(result['database_or_cloud_accessed'])
        self.assertFalse(result['deletion_performed'])

    def test_partial_evidence_never_passes(self):
        data=self.full_evidence();data['postgresql_isolated_restore']['decision']='pending'
        self.evidence.write_text(json.dumps({'schema_version':1,'evidence':data}))
        self.assertIn('postgresql_isolated_restore',evidence_state(self.evidence,today=self.TODAY)['missing_or_incomplete'])

    def test_bad_schema_version_fails_closed(self):
        self.full_evidence();x=json.loads(self.evidence.read_text());x['schema_version']=0
        self.evidence.write_text(json.dumps(x))
        self.assertFalse(evidence_state(self.evidence,today=self.TODAY)['present'])

    def test_corrupt_json_never_crashes_or_leaks(self):
        self.evidence.write_text('{"secret":"sk_live_ABC123', encoding='utf-8')
        result=evidence_state(self.evidence,today=self.TODAY)
        self.assertFalse(result['present'])
        self.assertNotIn('secret',json.dumps(result))

    def test_future_record_is_rejected(self):
        self.full_evidence(reviewed='2026-10-31')
        self.assertEqual(len(evidence_state(self.evidence,today=self.TODAY)['recorded']),0)

    def test_stale_record_is_rejected(self):
        self.full_evidence(reviewed='2024-09-01')
        self.assertEqual(len(evidence_state(self.evidence,today=self.TODAY)['recorded']),0)

    def test_invalid_calendar_day_is_rejected(self):
        self.full_evidence(reviewed='2026-02-30')
        self.assertEqual(len(evidence_state(self.evidence,today=self.TODAY)['recorded']),0)

    def test_bool_and_string_claims_cannot_fake_verification(self):
        for value in (True, 'verified', {'decision': True}, {'decision':'verified'}):
            self.assertFalse(_recorded(value,self.TODAY))

    def test_no_personal_reference_or_secret_in_result(self):
        entries=self.full_evidence()
        entries['controller_and_legal_text']['reference']='private-ticket-person-secret'
        self.evidence.write_text(json.dumps({'schema_version':1,'evidence':entries}))
        result=evidence_state(self.evidence,today=self.TODAY)
        self.assertNotIn('private-ticket-person-secret',json.dumps(result))
        self.assertEqual(len(result['recorded']),10)

    def test_placeholder_in_completed_retention_fields_is_rejected(self):
        self.full_policy()
        payload=json.loads(self.policy.read_text(encoding='utf-8'))
        payload['categories']['backups_and_restore_copies']['retention_rule']='TBD'
        self.policy.write_text(json.dumps(payload),encoding='utf-8')
        self.assertEqual(retention_state(self.policy)['status'],'manual_review_required')

    def test_placeholder_evidence_reference_is_rejected(self):
        items=self.full_evidence()
        items['controller_and_legal_text']['reference']='TODO'
        self.evidence.write_text(json.dumps({'schema_version':1,'evidence':items}))
        self.assertIn('controller_and_legal_text',evidence_state(self.evidence,today=self.TODAY)['missing_or_incomplete'])

    def test_oversized_evidence_is_not_parsed(self):
        self.evidence.write_text(' ' * 130000,encoding='utf-8')
        self.assertFalse(evidence_state(self.evidence,today=self.TODAY)['present'])

    def test_future_year_draft_marker_is_detected(self):
        self.legal.write_text('TERMS_VERSION="draft-2027-01-02"',encoding='utf-8')
        self.assertEqual(legal_source_state(self.legal),'draft_content')

    def test_completion_never_grants_approval_in_strict_cli(self):
        self.legal.write_text('TERMS_TITLE="Terms of Use"',encoding='utf-8')
        self.full_policy()
        from datetime import datetime, timezone
        current=datetime.now(timezone.utc).date().isoformat()
        self.full_evidence(reviewed=current)
        capture=StringIO()
        with contextlib.redirect_stdout(capture):
            code=main(['--backend',str(self.backend),'--retention-policy',str(self.policy),
                       '--evidence',str(self.evidence),'--strict'])
        self.assertEqual(code,0)
        report=json.loads(capture.getvalue())
        self.assertEqual(report['status'],'evidence_recorded_pending_independent_validation')
        self.assertFalse(report['approval_granted'])

    def test_template_contains_exact_required_names(self):
        example=json.loads((SCRIPT_DIR/'launch-evidence.example.json').read_text(encoding='utf-8'))
        self.assertEqual(set(example['evidence']),set(EVIDENCE_ITEMS))
        self.assertTrue(all(item['decision']=='pending' for item in example['evidence'].values()))

    def test_read_only_does_not_modify_inputs(self):
        self.full_evidence(); before=(self.policy.read_bytes(),self.evidence.read_bytes(),self.legal.read_bytes())
        audit(self.backend,retention_policy=self.policy,evidence_file=self.evidence,today=self.TODAY)
        self.assertEqual(before,(self.policy.read_bytes(),self.evidence.read_bytes(),self.legal.read_bytes()))

    def test_strict_cli_returns_nonzero_with_draft(self):
        capture=StringIO()
        with contextlib.redirect_stdout(capture):
            code=main(['--backend',str(self.backend),'--strict'])
        self.assertEqual(code,2)
        result=json.loads(capture.getvalue())
        self.assertEqual(result['status'],'incomplete')
        self.assertFalse(result['approval_granted'])

    def test_nonstrict_cli_reports_without_claiming_approval(self):
        capture=StringIO()
        with contextlib.redirect_stdout(capture):
            code=main(['--backend',str(self.backend)])
        self.assertEqual(code,0)
        self.assertFalse(json.loads(capture.getvalue())['approval_granted'])

    def test_launch_control_has_new_explicit_audit_command(self):
        source=(SCRIPT_DIR/'launch_control.py').read_text(encoding='utf-8')
        self.assertIn("'audit-launch'",source)
        self.assertIn("'--strict'",source)
        self.assertIn('EXPECTED_RELEASE = \'7.1.37\'',source)

    def test_cli_refuses_non_backend(self):
        capture=StringIO()
        with contextlib.redirect_stdout(capture):
            code=main(['--backend',str(self.root),'--strict'])
        self.assertEqual(code,2)
        self.assertNotIn(str(self.root),capture.getvalue())


if __name__ == '__main__':
    unittest.main()
