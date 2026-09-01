import json
from datetime import datetime
from pathlib import Path
import re
import unittest
from uuid import UUID


CONTRACTS = Path(__file__).parents[2] / "contracts" / "v1"
TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
LIGHT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
LIGHT_COMMAND_TYPES = {
    "light.command.power",
    "light.command.brightness",
    "light.command.rgb_color",
}
LIGHT_STATE_TYPES = {"light.state.reported", "light.state.changed"}


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise AssertionError(f"{path} must contain an object")
    return value


class ContractTests(unittest.TestCase):
    def test_light_schemas_are_versioned_and_use_the_common_envelope(self) -> None:
        light_schema = _load(CONTRACTS / "light.schema.json")
        capability_schema = _load(CONTRACTS / "light-capability.schema.json")
        command_schema = _load(CONTRACTS / "light-command.schema.json")
        state_schema = _load(CONTRACTS / "light-state.schema.json")

        for schema in (light_schema, capability_schema, command_schema, state_schema):
            self.assertEqual(
                schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )
            self.assertIn("https://openhdo.org/schemas/v1/", schema["$id"])

        self.assertEqual(command_schema["allOf"], [{"$ref": "envelope.schema.json"}])
        self.assertEqual(state_schema["allOf"], [{"$ref": "envelope.schema.json"}])
        manifest = _load(CONTRACTS / "link-manifest.schema.json")
        self.assertEqual(
            manifest["properties"]["devices"]["items"]["properties"]["capabilities"]["items"]["$ref"],
            "light-capability.schema.json",
        )
        self.assertTrue(capability_schema["additionalProperties"] is False)
        for forbidden in (
            "vendor",
            "model",
            "local_key",
            "pairing",
            "protocol",
            "dp_mapping",
        ):
            self.assertNotIn(forbidden, capability_schema["properties"])
        self.assertEqual(len(command_schema["oneOf"]), 3)
        self.assertEqual(len(state_schema["oneOf"]), 2)
        self.assertEqual(light_schema["$defs"]["brightness"]["minimum"], 0)
        self.assertEqual(light_schema["$defs"]["brightness"]["maximum"], 255)
        for branch in command_schema["oneOf"]:
            self.assertIn("correlation_id", branch["required"])
        self.assertIn("correlation_id", state_schema["oneOf"][1]["required"])
        for definition_name in (
            "power_command",
            "brightness_command",
            "rgb_color_command",
        ):
            self.assertTrue(
                {"light_id", "command_id", "idempotency_key"}
                <= set(light_schema["$defs"][definition_name]["required"])
            )
        self.assertEqual(
            {branch["properties"]["type"]["const"] for branch in command_schema["oneOf"]},
            LIGHT_COMMAND_TYPES,
        )
        self.assertEqual(
            {branch["properties"]["type"]["const"] for branch in state_schema["oneOf"]},
            LIGHT_STATE_TYPES,
        )
        self.assertEqual(
            {"power_command", "brightness_command", "rgb_color_command", "reported_state", "changed_state"},
            {ref["$ref"].split("#/$defs/")[-1] for ref in light_schema["oneOf"]},
        )

    def test_examples_preserve_envelope_and_light_identity_rules(self) -> None:
        examples = sorted((CONTRACTS / "examples").glob("*.json"))
        self.assertGreaterEqual(len(examples), 7)
        for path in examples:
            message = _load(path)
            self._assert_envelope(message)
            message_type = message["type"]
            payload = message["payload"]

            if message_type == "link.register":
                self.assertTrue({"id", "version", "name", "transports"} <= set(payload))
                self.assertRegex(payload["id"], LIGHT_ID_PATTERN)
                self.assertRegex(payload["version"], r"^\d+\.\d+\.\d+")
                self.assertIsInstance(payload["transports"], list)
                if "devices" in payload:
                    self._assert_devices(payload["devices"])
                continue

            if message_type in LIGHT_COMMAND_TYPES:
                self.assertIn("correlation_id", message)
                self._assert_command_metadata(payload)
                self.assertRegex(payload["light_id"], LIGHT_ID_PATTERN)
                if message_type == "light.command.power":
                    self.assertIs(type(payload.get("power")), bool)
                elif message_type == "light.command.brightness":
                    self._assert_brightness(payload["brightness"])
                else:
                    self._assert_rgb(payload["rgb_color"])
                continue

            self.assertIn(message_type, LIGHT_STATE_TYPES)
            self._assert_state(payload)
            if message_type == "light.state.changed":
                self.assertIn("correlation_id", message)
                self._assert_command_metadata(payload)

    def _assert_envelope(self, message: dict) -> None:
        self.assertEqual(message["v"], 1)
        UUID(message["id"])
        self.assertRegex(message["type"], TYPE_PATTERN)
        datetime.fromisoformat(message["ts"].replace("Z", "+00:00"))
        self.assertTrue(isinstance(message["source"], str) and message["source"])
        self.assertIsInstance(message["payload"], dict)
        if "correlation_id" in message:
            UUID(message["correlation_id"])

    def _assert_command_metadata(self, payload: dict) -> None:
        UUID(payload["command_id"])
        self.assertIs(type(payload["idempotency_key"]), str)
        self.assertGreater(len(payload["idempotency_key"]), 0)

    def _assert_state(self, payload: dict) -> None:
        self.assertRegex(payload["light_id"], LIGHT_ID_PATTERN)
        self.assertIs(type(payload["power"]), bool)
        self._assert_brightness(payload["brightness"])
        self._assert_rgb(payload["rgb_color"])
        self.assertIs(type(payload["state_revision"]), int)
        self.assertGreaterEqual(payload["state_revision"], 0)

    def _assert_devices(self, devices: object) -> None:
        self.assertIsInstance(devices, list)
        self.assertGreater(len(devices), 0)
        for device in devices:
            self.assertIsInstance(device, dict)
            self.assertRegex(device["id"], LIGHT_ID_PATTERN)
            self.assertTrue(isinstance(device["name"], str) and device["name"])
            capabilities = device["capabilities"]
            self.assertIsInstance(capabilities, list)
            self.assertGreater(len(capabilities), 0)
            for capability in capabilities:
                self.assertEqual(capability["kind"], "light")
                self.assertIs(type(capability["power"]), bool)
                self.assertEqual(capability["brightness"], {"min": 0, "max": 255})
                if "color_modes" in capability:
                    self.assertTrue(
                        set(capability["color_modes"]) <= {"RGB", "RGBW", "CCT"}
                    )
                if "rgb_channel_range" in capability:
                    self.assertTrue(
                        {"RGB", "RGBW"} & set(capability["color_modes"])
                    )
                    self.assertEqual(
                        capability["rgb_channel_range"], {"min": 0, "max": 255}
                    )
                for forbidden in (
                    "vendor",
                    "model",
                    "local_key",
                    "pairing",
                    "protocol",
                    "dp_mapping",
                ):
                    self.assertNotIn(forbidden, capability)

    def _assert_brightness(self, value: object) -> None:
        self.assertIs(type(value), int)
        self.assertGreaterEqual(value, 0)
        self.assertLessEqual(value, 255)

    def _assert_rgb(self, value: object) -> None:
        self.assertIsInstance(value, dict)
        self.assertEqual(set(value), {"r", "g", "b"})
        for channel in value.values():
            self.assertIs(type(channel), int)
            self.assertGreaterEqual(channel, 0)
            self.assertLessEqual(channel, 255)


if __name__ == "__main__":
    unittest.main()
