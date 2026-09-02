import json
import tempfile
import unittest
from pathlib import Path

from openhdo_linker_service.runtime import LinkerConfigError, load_config


class LinkerServiceConfigTests(unittest.TestCase):
    def test_loads_discovery_only_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "listen": {"host": "0.0.0.0", "port": 8765, "secret": "linker1"},
                        "discovery": {"enabled": True, "timeout_s": 5},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.linker_id, "openhdo.linker.rgb-light")
        self.assertTrue(config.discovery_enabled)
        self.assertIsNone(config.tuya)

    def test_rejects_out_of_range_discovery_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "listen": {"secret": "linker1"},
                        "discovery": {"timeout_s": 61},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LinkerConfigError):
                load_config(path)
