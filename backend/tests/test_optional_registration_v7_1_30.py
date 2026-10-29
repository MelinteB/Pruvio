"""Execute the actual FastAPI registration handler with isolated service dependencies.

The full registration OTP/email service has its own tests; these tests ensure the
React-facing route no longer makes browser push permission a prerequisite.
"""
import ast
import copy
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def isolated_registration_handler():
    source = (ROOT / 'app/react_app/api.py').read_text(encoding='utf8')
    tree = ast.parse(source)
    handler = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'register')
    handler = copy.deepcopy(handler)
    handler.decorator_list = []
    handler.args.defaults = []  # supply db explicitly; do not load production dependencies
    handler.args.args[-1].annotation = None
    handler.args.args[-2].annotation = None
    scope = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[handler],type_ignores=[])),
                 str(ROOT / 'app/react_app/api.py'), 'exec'), scope)
    return scope['register'], scope


class OptionalRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.register, self.scope = isolated_registration_handler()
        self.db = Mock()
        self.user = types.SimpleNamespace(notifications_opt_in=None, email='new@example.org')
        self.onboarding = Mock()
        self.onboarding.start_registration.return_value = {
            'user': self.user, 'challenge_id': 'otp-abc', 'email_delivery': {'sent': True}
        }
        self.rate_limit = Mock()
        self.scope.update(onboarding=self.onboarding, limit=self.rate_limit)

    def call(self, **overrides):
        payload = dict(password='valid-password', accepted_terms=True, accepted_privacy=True,
                       phone_number='+40000001234', name='Guest', email='new@example.org')
        payload.update(overrides)
        return self.register(payload, types.SimpleNamespace(), self.db)

    def test_no_push_or_notification_fields_still_starts_verification(self):
        response = self.call()
        self.assertEqual(response['challenge_id'], 'otp-abc')
        self.assertFalse(self.user.notifications_opt_in)
        self.onboarding.start_registration.assert_called_once()
        self.db.commit.assert_called_once()
        self.rate_limit.assert_called_once()

    def test_explicit_notification_consent_can_be_saved_without_device_permission(self):
        self.call(notifications_opt_in=True)
        self.assertTrue(self.user.notifications_opt_in)

    def test_a_forged_push_permission_does_not_enable_notification_consent(self):
        self.call(notifications_opt_in=False, notification_permission='granted')
        self.assertFalse(self.user.notifications_opt_in)

    def test_nonboolean_notification_consent_does_not_opt_in(self):
        self.call(notifications_opt_in='true')
        self.assertFalse(self.user.notifications_opt_in)

    def test_empty_password_rejected_without_starting_registration(self):
        with self.assertRaises(ValueError):
            self.call(password='')
        self.onboarding.start_registration.assert_not_called()

    def test_legal_acceptance_is_passed_through_for_service_validation(self):
        self.call(accepted_terms=False,accepted_privacy=False)
        kwargs = self.onboarding.start_registration.call_args.kwargs
        self.assertFalse(kwargs['accepted_terms'])
        self.assertFalse(kwargs['accepted_privacy'])

    def test_no_browser_permission_gate_remains_in_registration_ui(self):
        src=(ROOT/'frontend/src/Auth.jsx').read_text(encoding='utf8')
        self.assertNotIn('Notification.requestPermission()',src)
        self.assertNotIn('notification_permission:',src)
        self.assertIn('notifications_opt_in:form.notifications_opt_in === true',src)
        self.assertIn('Receive bill and payment notifications (optional)',src)


if __name__ == '__main__':
    unittest.main()
