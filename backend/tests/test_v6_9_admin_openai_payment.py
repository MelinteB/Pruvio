import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

try:
    from azure.core.credentials import AzureKeyCredential  # noqa: F401
    from azure.ai.documentintelligence import DocumentIntelligenceClient  # noqa: F401
except ImportError:
    azure = types.ModuleType("azure")
    azure_core = types.ModuleType("azure.core")
    azure_core_credentials = types.ModuleType("azure.core.credentials")
    azure_ai = types.ModuleType("azure.ai")
    azure_ai_documentintelligence = types.ModuleType("azure.ai.documentintelligence")
    azure_core_credentials.AzureKeyCredential = object
    azure_ai_documentintelligence.DocumentIntelligenceClient = object
    sys.modules["azure"] = azure
    sys.modules["azure.core"] = azure_core
    sys.modules["azure.core.credentials"] = azure_core_credentials
    sys.modules["azure.ai"] = azure_ai
    sys.modules["azure.ai.documentintelligence"] = azure_ai_documentintelligence

try:
    import openai  # noqa: F401
except ImportError:
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = object
    sys.modules["openai"] = fake_openai

from app.api.openai_api import openai_status
from app.api.users import delete_user_by_id, require_admin_api_key
from app.api.split_bill_sessions import start_participant_payment


class AdminDeletionTests(unittest.TestCase):
    def test_admin_key_accepts_configured_value(self):
        with patch.dict(os.environ, {"PRUVIO_ADMIN_API_KEY": "test-admin-key"}, clear=False):
            require_admin_api_key("test-admin-key")

    def test_admin_key_rejects_wrong_value(self):
        with patch.dict(os.environ, {"PRUVIO_ADMIN_API_KEY": "test-admin-key"}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                require_admin_api_key("wrong")
            self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.api.users.delete_user_completely")
    def test_admin_delete_does_not_require_verified_email_or_otp(self, delete_user_completely):
        user = SimpleNamespace(
            id=42,
            email=None,
            is_email_verified=False,
            status="pending",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user

        result = delete_user_by_id(42, db)

        delete_user_completely.assert_called_once_with(db, user)
        self.assertEqual(result["deleted"], True)
        self.assertEqual(result["verification_required"], False)


class OpenAIAdminApiTests(unittest.TestCase):
    def test_openai_receipt_direct_service_imports(self):
        from app.services.openai_receipt_direct_service import (
            process_document_with_openai_receipt_direct,
        )
        self.assertTrue(callable(process_document_with_openai_receipt_direct))

    def test_status_does_not_expose_api_key(self):
        env = {
            "OPENAI_API_KEY": "secret-test-key",
            "OPENAI_RECEIPT_MODEL": "gpt-6-luna",
            "OPENAI_TRANSLATION_MODEL": "gpt-6-luna",
            "OPENAI_RECEIPT_FALLBACK_ENABLED": "true",
            "OPENAI_TRANSLATION_FALLBACK_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            result = openai_status()
        self.assertTrue(result["configured"])
        self.assertNotIn("api_key", result)
        self.assertEqual(result["receipt_model"], "gpt-6-luna")


class PaymentStartApiTests(unittest.TestCase):
    @patch("app.api.split_bill_sessions.record_participant_payment_status")
    @patch("app.api.split_bill_sessions.get_split_bill_participant_by_token")
    @patch("app.api.split_bill_sessions.get_split_bill_session_by_token")
    def test_participant_token_starts_revolut_payment(
        self,
        get_session,
        get_participant,
        record_payment,
    ):
        session = SimpleNamespace(id=7)
        participant = SimpleNamespace(id=9, session_id=7)
        get_session.return_value = session
        get_participant.return_value = participant
        db = MagicMock()

        result = start_participant_payment(
            token="session-token",
            participant_token="participant-token",
            method="revolut",
            db=db,
        )

        record_payment.assert_called_once_with(
            db=db,
            session=session,
            participant_id=9,
            method="revolut",
            paid=False,
        )
        self.assertEqual(result["status"], "initiated")
        self.assertEqual(result["method"], "revolut")


if __name__ == "__main__":
    unittest.main()
