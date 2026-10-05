import os
import unittest
from unittest.mock import patch

from app.services.browser_upload_token_service import (
    create_browser_upload_token,
    verify_browser_upload_token,
)


class BrowserUploadTokenTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get("PRUVS_UPLOAD_TOKEN_SECRET")
        os.environ["PRUVS_UPLOAD_TOKEN_SECRET"] = "v6.8-test-secret"

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("PRUVS_UPLOAD_TOKEN_SECRET", None)
        else:
            os.environ["PRUVS_UPLOAD_TOKEN_SECRET"] = self.previous

    def test_round_trip(self):
        with patch("app.services.browser_upload_token_service.time.time", return_value=1_000):
            token = create_browser_upload_token(123, ttl_seconds=120)
        with patch("app.services.browser_upload_token_service.time.time", return_value=1_050):
            self.assertEqual(verify_browser_upload_token(token), 123)

    def test_tampered_token_is_rejected(self):
        token = create_browser_upload_token(123)
        with self.assertRaises(ValueError):
            verify_browser_upload_token(token + "x")

    def test_expired_token_is_rejected(self):
        with patch("app.services.browser_upload_token_service.time.time", return_value=1_000):
            token = create_browser_upload_token(123, ttl_seconds=60)
        with patch("app.services.browser_upload_token_service.time.time", return_value=1_061):
            with self.assertRaisesRegex(ValueError, "expired"):
                verify_browser_upload_token(token)


if __name__ == "__main__":
    unittest.main()
