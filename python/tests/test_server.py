from pathlib import Path
import unittest
from openhdo_server.config import load_settings, SettingsError

class ConfigurationTests(unittest.TestCase):
    def test_defaults_are_local_and_non_local_bind_requires_token(self) -> None:
        settings = load_settings({})
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.auth_db_path, str(Path(__file__).resolve().parents[2] / "data" / "openhdo-auth.sqlite3"))
        with self.assertRaises(SettingsError):
            load_settings({"OPENHDO_HOST": "0.0.0.0"})
        settings = load_settings({"OPENHDO_HOST": "0.0.0.0", "OPENHDO_API_TOKEN": "long-enough-token"})
        self.assertEqual(settings.port, 8000)

    def test_cors_origins_are_loaded_as_exact_comma_separated_origins(self) -> None:
        settings = load_settings(
            {"OPENHDO_CORS_ORIGINS": " http://localhost:5173,https://dashboard.example "}
        )
        self.assertEqual(settings.cors_origins, ("http://localhost:5173", "https://dashboard.example"))
        with self.assertRaises(SettingsError):
            load_settings({"OPENHDO_CORS_ORIGINS": "*"})
