import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.api.users import _validate_admin_api_key
from app.schemas.user import UserAdminUpdate
from app.services.user_service import update_user_admin


class AdminKeyV610Tests(unittest.TestCase):
    def test_new_pruvs_admin_env_name_is_preferred(self):
        with patch.dict(
            os.environ,
            {"PRUVS_ADMIN_API_KEY": "new-key", "PRUVIO_ADMIN_API_KEY": "legacy-key"},
            clear=False,
        ):
            _validate_admin_api_key("new-key")

    def test_legacy_admin_env_name_still_works(self):
        with patch.dict(os.environ, {"PRUVIO_ADMIN_API_KEY": "legacy-key"}, clear=False):
            os.environ.pop("PRUVS_ADMIN_API_KEY", None)
            _validate_admin_api_key("legacy-key")


class AdminUserUpdateTests(unittest.TestCase):
    def _user(self):
        return SimpleNamespace(
            id=7,
            username="old.user",
            username_key="old.user",
            phone_number="+40700000000",
            name="Old User",
            email="old@example.com",
            status="active",
            is_phone_verified=True,
            is_email_verified=True,
            preferred_language="en",
            marketing_opt_in=False,
            notifications_opt_in=True,
            revolut_payment_link=None,
            payment_recipient_name=None,
            payment_iban=None,
            payment_bank_name=None,
            payment_bic=None,
            payment_note=None,
            updated_at=None,
        )

    def _db_without_conflicts(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    def test_email_can_be_changed_without_otp_and_verification_is_reset(self):
        user = self._user()
        db = self._db_without_conflicts()
        payload = UserAdminUpdate(email="new@example.com", name="New User")

        result = update_user_admin(db, user, payload)

        self.assertIs(result, user)
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.name, "New User")
        self.assertFalse(user.is_email_verified)
        db.commit.assert_called_once()

    def test_admin_can_explicitly_mark_new_email_verified(self):
        user = self._user()
        db = self._db_without_conflicts()
        payload = UserAdminUpdate(email="verified@example.com", is_email_verified=True)

        update_user_admin(db, user, payload)

        self.assertEqual(user.email, "verified@example.com")
        self.assertTrue(user.is_email_verified)

    def test_phone_change_resets_phone_verification_unless_explicit(self):
        user = self._user()
        db = self._db_without_conflicts()
        payload = UserAdminUpdate(phone_number="0722 123 456")

        update_user_admin(db, user, payload)

        self.assertEqual(user.phone_number, "+40722123456")
        self.assertFalse(user.is_phone_verified)

    def test_sensitive_fields_are_not_accepted_by_admin_patch_schema(self):
        with self.assertRaises(ValidationError):
            UserAdminUpdate(password_hash="should-never-be-editable")
        with self.assertRaises(ValidationError):
            UserAdminUpdate(accepted_terms=True)


if __name__ == "__main__":
    unittest.main()
