from __future__ import annotations

from datetime import datetime, timezone
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from openhdo_server.app import create_app
from openhdo_server.config import ServerSettings, SettingsError, load_settings


def envelope(message_type: str, source: str, payload: dict, **extra: object) -> dict:
    message = {
        "v": 1,
        "id": str(uuid4()),
        "type": message_type,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": source,
        "payload": payload,
    }
    message.update(extra)
    return message


def light_capability() -> dict:
    return {
        "kind": "light",
        "power": True,
        "brightness": {"min": 0, "max": 255},
        "color_modes": ["RGB"],
        "rgb_channel_range": {"min": 0, "max": 255},
    }


def register_message() -> dict:
    return envelope(
        "link.register",
        "linker.test",
        {
            "id": "linker.test",
            "version": "1.0.0",
            "name": "Test Linker",
            "transports": ["local"],
            "devices": [
                {"id": "light.living", "name": "Living room", "capabilities": [light_capability()]}
            ],
        },
    )


def reported_state(brightness: int, revision: int, **extra: object) -> dict:
    return envelope(
        "light.state.reported",
        "linker.test",
        {
            "light_id": "light.living",
            "power": True,
            "brightness": brightness,
            "rgb_color": {"r": 1, "g": 2, "b": 3},
            "state_revision": revision,
        },
        **extra,
    )


class ConfigurationTests(unittest.TestCase):
    def test_defaults_are_local_and_non_local_bind_requires_token(self) -> None:
        self.assertEqual(load_settings({}).host, "127.0.0.1")
        with self.assertRaises(SettingsError):
            load_settings({"OPENHDO_HOST": "0.0.0.0"})
        settings = load_settings({"OPENHDO_HOST": "0.0.0.0", "OPENHDO_API_TOKEN": "long-enough-token"})
        self.assertEqual(settings.port, 8000)


class ServerApiTests(unittest.TestCase):
    def test_health_and_empty_inventory(self) -> None:
        with TestClient(create_app(ServerSettings())) as client:
            health = client.get("/api/v1/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["runtime"], "python")
            self.assertEqual(client.get("/api/v1/lights").json(), {"api_version": 1, "lights": []})

    def test_linker_registers_state_and_receives_command_result_path(self) -> None:
        with TestClient(create_app(ServerSettings())) as client:
            with client.websocket_connect("/api/v1/events") as events:
                with client.websocket_connect("/api/v1/linkers/linker.test") as linker:
                    linker.send_json(register_message())
                    registered = events.receive_json()
                    self.assertEqual(registered["type"], "light.updated")
                    self.assertIsNone(registered["payload"]["state"])

                    listing = client.get("/api/v1/lights").json()
                    self.assertEqual(listing["lights"][0]["capability"]["brightness"]["max"], 255)

                    linker.send_json(reported_state(200, 1))
                    state_event = events.receive_json()
                    self.assertEqual(state_event["payload"]["state"]["brightness"], 200)

                    command_id = uuid4()
                    request_correlation_id = uuid4()
                    command = envelope(
                        "light.command.brightness",
                        "client.dashboard",
                        {
                            "light_id": "light.living",
                            "command_id": str(command_id),
                            "idempotency_key": "living-brightness-1",
                            "brightness": 255,
                        },
                        correlation_id=str(request_correlation_id),
                    )
                    accepted = client.post("/api/v1/lights/light.living/commands", json=command)
                    self.assertEqual(accepted.status_code, 202)
                    self.assertEqual(accepted.json()["payload"]["status"], "accepted")
                    forwarded = linker.receive_json()
                    self.assertEqual(forwarded["source"], "openhdo-server")
                    self.assertEqual(forwarded["payload"]["brightness"], 255)
                    self.assertEqual(accepted.json()["correlation_id"], forwarded["id"])

                    duplicate = client.post("/api/v1/lights/light.living/commands", json=command)
                    self.assertEqual(duplicate.status_code, 202)
                    self.assertEqual(duplicate.json()["id"], accepted.json()["id"])

                    linker.send_json(
                        envelope(
                            "command.result",
                            "linker.test",
                            {
                                "status": "applied",
                                "light_id": "light.living",
                                "command_id": str(command_id),
                                "idempotency_key": "living-brightness-1",
                                "state": {
                                    "light_id": "light.living",
                                    "power": True,
                                    "brightness": 255,
                                    "rgb_color": {"r": 1, "g": 2, "b": 3},
                                    "state_revision": 2,
                                },
                            },
                            correlation_id=forwarded["id"],
                        )
                    )
                    applied = events.receive_json()
                    self.assertEqual(applied["type"], "light.updated")
                    self.assertEqual(applied["correlation_id"], forwarded["id"])
                    self.assertEqual(client.get("/api/v1/lights/light.living").json()["state"]["brightness"], 255)

    def test_patch_maps_to_a_typed_light_command(self) -> None:
        with TestClient(create_app(ServerSettings())) as client:
            with client.websocket_connect("/api/v1/linkers/linker.test") as linker:
                linker.send_json(register_message())
                response = client.patch(
                    "/api/v1/lights/light.living",
                    json={"brightness": 0, "idempotency_key": "patch-brightness-1"},
                )
                self.assertEqual(response.status_code, 202)
                forwarded = linker.receive_json()
                self.assertEqual(forwarded["type"], "light.command.brightness")
                self.assertEqual(forwarded["payload"]["brightness"], 0)

    def test_admin_panel_is_optional_and_has_a_server_owned_path(self) -> None:
        application = create_app(ServerSettings())
        with TestClient(application) as client:
            response = client.get("/admin")
            if application.state.admin_panel_available:
                self.assertEqual(response.status_code, 200)
                self.assertIn("<html", response.text.lower())
            else:
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["error"], "admin_panel_unavailable")

    def test_invalid_brightness_is_rejected_and_disconnected_linker_is_not_success(self) -> None:
        with TestClient(create_app(ServerSettings())) as client:
            invalid = envelope(
                "light.command.brightness",
                "client.dashboard",
                {
                    "light_id": "light.living",
                    "command_id": str(uuid4()),
                    "idempotency_key": "invalid",
                    "brightness": 256,
                },
                correlation_id=str(uuid4()),
            )
            self.assertEqual(client.post("/api/v1/lights/light.living/commands", json=invalid).status_code, 422)

            with client.websocket_connect("/api/v1/linkers/linker.test") as linker:
                linker.send_json(register_message())
            command = envelope(
                "light.command.power",
                "client.dashboard",
                {
                    "light_id": "light.living",
                    "command_id": str(uuid4()),
                    "idempotency_key": "unavailable",
                    "power": True,
                },
                correlation_id=str(uuid4()),
            )
            response = client.post("/api/v1/lights/light.living/commands", json=command)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"], "linker_unavailable")

    def test_bearer_token_is_required_for_control_boundaries(self) -> None:
        settings = ServerSettings(api_token="long-enough-token")
        application = create_app(settings)
        with TestClient(application) as client:
            self.assertEqual(client.get("/api/v1/health").status_code, 200)
            self.assertEqual(client.get("/api/v1/lights").status_code, 401)
            self.assertEqual(client.get("/admin").status_code, 401)
            self.assertEqual(
                client.get("/api/v1/lights", headers={"Authorization": "Bearer long-enough-token"}).status_code,
                200,
            )
            admin = client.get("/admin", headers={"Authorization": "Bearer long-enough-token"})
            self.assertEqual(admin.status_code, 200 if application.state.admin_panel_available else 404)


if __name__ == "__main__":
    unittest.main()
