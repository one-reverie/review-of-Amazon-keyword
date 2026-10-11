from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from token_analyzer.settings import ModelProfile, ModelSettingsStore


class SettingsTests(unittest.TestCase):
    def test_model_profile_round_trip_is_encrypted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = ModelSettingsStore(path)
            secret = "test-secret-not-real"
            profile = ModelProfile(
                provider="自定义服务商",
                base_url="https://example.invalid/v1",
                model="example-model",
                api_key=secret,
            )
            store.save(profile)
            loaded = store.load()

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded, profile)
            self.assertNotIn(secret, path.read_text(encoding="utf-8"))

    def test_custom_weights_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ModelSettingsStore(Path(directory) / "settings.json")
            weights = {
                "orders": 0.40,
                "clicks": 0.20,
                "impressions": 0.10,
                "cvr": 0.15,
                "ctr": 0.10,
                "frequency": 0.05,
            }
            store.save_custom_weights(weights)

            self.assertEqual(store.load_custom_weights(), weights)


if __name__ == "__main__":
    unittest.main()
