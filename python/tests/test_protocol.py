import unittest
from uuid import uuid4

from openhdo_sdk import Envelope, LinkerManifest, ProtocolError


class EnvelopeTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        envelope = Envelope("link.register", "linker.test", {"name": "Test"})
        decoded = Envelope.from_json(envelope.to_json())

        self.assertEqual(decoded.type, envelope.type)
        self.assertEqual(decoded.source, envelope.source)
        self.assertEqual(decoded.payload, envelope.payload)
        self.assertEqual(decoded.id, envelope.id)

    def test_rejects_unknown_version(self) -> None:
        with self.assertRaises(ProtocolError):
            Envelope.from_dict(
                {
                    "v": 2,
                    "id": str(uuid4()),
                    "type": "link.register",
                    "ts": "2026-01-01T00:00:00Z",
                    "source": "test",
                    "payload": {},
                }
            )

    def test_rejects_invalid_type(self) -> None:
        with self.assertRaises(ProtocolError):
            Envelope("Link.Register", "test", {})

    def test_rejects_invalid_identity(self) -> None:
        with self.assertRaises(ProtocolError):
            Envelope("link.register", "test", {}, id="not-a-uuid")  # type: ignore[arg-type]

    def test_linker_manifest_creates_registration(self) -> None:
        message = LinkerManifest(
            "linker.test", "0.1.0", "Test Linker", ("zigbee", "bluetooth")
        ).registration("linker.test")

        self.assertEqual(message.type, "link.register")
        self.assertEqual(message.payload["transports"], ["zigbee", "bluetooth"])


if __name__ == "__main__":
    unittest.main()
