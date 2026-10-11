from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from token_analyzer.activation import ActivationStore, PRODUCT_ID, default_activation_path, verify_activation_code


TEST_ACTIVATION_CODE = "test-enterprise-code"


def _test_activation_digest() -> bytes:
    return hashlib.sha256(f"{PRODUCT_ID}|{TEST_ACTIVATION_CODE}".encode("utf-8")).digest()


class ActivationTests(unittest.TestCase):
    def test_only_the_internal_activation_code_is_accepted(self) -> None:
        with patch("token_analyzer.activation._ACTIVATION_CODE_DIGEST", _test_activation_digest()):
            self.assertTrue(verify_activation_code(TEST_ACTIVATION_CODE))
            self.assertTrue(verify_activation_code(f" {TEST_ACTIVATION_CODE} "))
            self.assertFalse(verify_activation_code("wrong"))
            self.assertFalse(verify_activation_code(""))

    def test_store_encrypts_activation_marker_and_automatically_recognizes_it(self) -> None:
        encrypted_values: dict[str, str] = {}

        def fake_protect(value: str) -> str:
            encrypted_values["opaque-dpapi-value"] = value
            return "opaque-dpapi-value"

        def fake_unprotect(value: str) -> str:
            return encrypted_values[value]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activation.json"
            with (
                patch("token_analyzer.activation._ACTIVATION_CODE_DIGEST", _test_activation_digest()),
                patch("token_analyzer.activation.protect_secret", side_effect=fake_protect),
                patch("token_analyzer.activation.unprotect_secret", side_effect=fake_unprotect),
            ):
                store = ActivationStore(path)
                self.assertFalse(store.activate("wrong"))
                self.assertFalse(path.exists())
                self.assertTrue(store.activate(TEST_ACTIVATION_CODE))
                self.assertTrue(store.is_activated())

            stored_text = path.read_text(encoding="utf-8")
            self.assertNotIn(TEST_ACTIVATION_CODE, stored_text)
            self.assertEqual(json.loads(stored_text)["credential_encrypted"], "opaque-dpapi-value")

    def test_damaged_old_or_unreadable_credentials_require_activation_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activation.json"
            store = ActivationStore(path)
            path.write_text("{broken", encoding="utf-8")
            self.assertFalse(store.is_activated())

            path.write_text(
                json.dumps({"version": 1, "credential_encrypted": "old-format"}),
                encoding="utf-8",
            )
            self.assertFalse(store.is_activated())

            path.write_text(
                json.dumps({"version": 2, "credential_encrypted": "damaged"}),
                encoding="utf-8",
            )
            with patch("token_analyzer.activation.unprotect_secret", side_effect=OSError("DPAPI failed")):
                self.assertFalse(store.is_activated())

    def test_default_path_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertEqual(default_activation_path(), Path(directory) / "TokenAnalyzer" / "activation.json")


if __name__ == "__main__":
    unittest.main()
