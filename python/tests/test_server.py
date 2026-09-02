from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest
import time
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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


def create_linker_app(settings: ServerSettings | None = None, *, register: bool = True):
    data_directory = TemporaryDirectory()
    application = create_app(
        (settings or ServerSettings()).model_copy(update={"data_dir": data_directory.name})
    )
    application.state.test_data_directory = data_directory
    if register:
        application.state.linker_registry.add("linker.test", "Test Linker")
    return application


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


def discovery_candidate(session_id: str, correlation_id: str, **extra: object) -> dict:
    return envelope(
        "discovery.candidate",
        "linker.test",
        {
            "session_id": session_id,
            "candidate_id": "light.discovered",
            "name": "Discovered light",
            "transport": "wifi",
            "capabilities": [light_capability()],
            "requires_pairing": True,
        },
        correlation_id=correlation_id,
        **extra,
    )


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


class ServerApiTests(unittest.TestCase):
    def test_configured_cors_is_explicit_and_does_not_change_bearer_auth(self) -> None:
        settings = ServerSettings(
            api_token="long-enough-token", cors_origins=("http://localhost:5173",)
        )
        with TestClient(create_app(settings)) as client:
            preflight = client.options(
                "/api/v1/lights",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "authorization,content-type,accept,x-openhdo-source",
                },
            )
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(preflight.headers["access-control-allow-origin"], "http://localhost:5173")
            self.assertEqual(preflight.headers["access-control-allow-methods"], "GET, PATCH, POST, DELETE")
            self.assertNotIn("access-control-allow-credentials", preflight.headers)
            self.assertEqual(
                client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"}).headers[
                    "access-control-allow-origin"
                ],
                "http://localhost:5173",
            )
            self.assertNotIn(
                "access-control-allow-origin",
                client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"}).headers,
            )
            self.assertEqual(client.get("/api/v1/lights").status_code, 401)

    def test_configured_origin_allowlist_handles_browser_and_native_websockets(self) -> None:
        settings = ServerSettings(cors_origins=("http://localhost:5173",))
        with TestClient(create_linker_app(settings)) as client:
            for headers in ({}, {"Origin": "http://localhost:3000"}):
                with self.assertRaises(WebSocketDisconnect) as error:
                    with client.websocket_connect("/api/v1/events", headers=headers):
                        pass
                self.assertEqual(error.exception.code, 4403)

            with self.assertRaises(WebSocketDisconnect) as error:
                with client.websocket_connect(
                    "/api/v1/linkers/linker.test", headers={"Origin": "http://localhost:3000"}
                ):
                    pass
            self.assertEqual(error.exception.code, 4403)

            with client.websocket_connect(
                "/api/v1/events", headers={"Origin": "http://localhost:5173"}
            ) as events:
                events.close()
            with client.websocket_connect(
                "/api/v1/linkers/linker.test"
            ) as linker:
                linker.close()

    def test_health_and_empty_inventory(self) -> None:
        with TestClient(create_app(ServerSettings())) as client:
            health = client.get("/api/v1/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["runtime"], "python")
            self.assertEqual(client.get("/api/v1/lights").json(), {"api_version": 1, "lights": []})

    def test_linkers_list_manifest_availability_and_devices(self) -> None:
        application = create_linker_app(register=False)
        with TestClient(application) as client:
            self.assertEqual(client.get("/api/v1/linkers").json(), {"api_version": 1, "linkers": []})
            application.state.linker_registry.add("linker.test", "Test Linker")
            with client.websocket_connect("/api/v1/linkers/linker.test") as linker:
                linker.send_json(register_message())
                listed = client.get("/api/v1/linkers")
                self.assertEqual(listed.status_code, 200)
                linker_view = listed.json()["linkers"][0]
                self.assertTrue(linker_view["available"])
                self.assertEqual(linker_view["transports"], ["local"])
                self.assertEqual(linker_view["devices"][0]["light_id"], "light.living")
            self.assertFalse(client.get("/api/v1/linkers").json()["linkers"][0]["available"])

    def test_unregistered_linker_is_rejected_before_registration(self) -> None:
        with TestClient(create_linker_app(register=False)) as client:
            with self.assertRaises(WebSocketDisconnect) as error:
                with client.websocket_connect("/api/v1/linkers/linker.test"):
                    pass
            self.assertEqual(error.exception.code, 1008)

    def test_linker_registers_state_and_receives_command_result_path(self) -> None:
        with TestClient(create_linker_app()) as client:
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
        with TestClient(create_linker_app()) as client:
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

    def test_discovery_session_uses_linker_socket_and_keeps_real_empty_scan_empty(self) -> None:
        with TestClient(create_linker_app()) as client:
            with client.websocket_connect("/api/v1/linkers/linker.test") as linker:
                linker.send_json(register_message())
                response = client.post(
                    "/api/v1/discovery/sessions",
                    json={"linker_id": "linker.test", "timeout_s": 3},
                )
                self.assertEqual(response.status_code, 202)
                session = response.json()
                self.assertEqual(
                    session,
                    {
                        "session_id": session["session_id"],
                        "linker_id": "linker.test",
                        "status": "running",
                        "candidates": [],
                        "error": None,
                    },
                )

                start = linker.receive_json()
                self.assertEqual(start["type"], "discovery.start")
                self.assertEqual(start["correlation_id"], start["id"])
                self.assertEqual(start["payload"]["session_id"], session["session_id"])
                self.assertEqual(start["payload"]["timeout_s"], 3)

                empty = client.get(f"/api/v1/discovery/sessions/{session['session_id']}")
                self.assertEqual(empty.status_code, 200)
                self.assertEqual(empty.json()["candidates"], [])

                linker.send_json(discovery_candidate(session["session_id"], start["id"]))
                candidate = client.get(f"/api/v1/discovery/sessions/{session['session_id']}").json()
                self.assertEqual(candidate["candidates"][0]["candidate_id"], "light.discovered")
                self.assertTrue(candidate["candidates"][0]["requires_pairing"])
                self.assertNotIn("vendor", candidate["candidates"][0])

                linker.send_json(
                    envelope(
                        "discovery.completed",
                        "linker.test",
                        {"session_id": session["session_id"], "status": "completed", "error": None},
                        correlation_id=start["id"],
                    )
                )
                completed = client.get(f"/api/v1/discovery/sessions/{session['session_id']}").json()
                self.assertEqual(completed["status"], "completed")

    def test_discovery_timeout_and_unavailable_linker_are_explicit_failures(self) -> None:
        with TestClient(create_linker_app()) as client:
            unavailable = client.post(
                "/api/v1/discovery/sessions",
                json={"linker_id": "linker.test", "timeout_s": 1},
            )
            self.assertEqual(unavailable.status_code, 202)
            self.assertEqual(unavailable.json()["status"], "failed")
            self.assertIn("not connected", unavailable.json()["error"])

            with client.websocket_connect("/api/v1/linkers/linker.test") as linker:
                linker.send_json(register_message())
                response = client.post(
                    "/api/v1/discovery/sessions",
                    json={"linker_id": "linker.test", "timeout_s": 1},
                )
                session_id = response.json()["session_id"]
                linker.receive_json()
                time.sleep(1.2)
                timed_out = client.get(f"/api/v1/discovery/sessions/{session_id}").json()
                self.assertEqual(timed_out["status"], "failed")
                self.assertEqual(timed_out["error"], "discovery timed out")

    def test_linker_disconnect_terminally_fails_running_discovery(self) -> None:
        with TestClient(create_linker_app()) as client:
            with client.websocket_connect("/api/v1/linkers/linker.test") as linker:
                linker.send_json(register_message())
                response = client.post(
                    "/api/v1/discovery/sessions",
                    json={"linker_id": "linker.test", "timeout_s": 60},
                )
                session_id = response.json()["session_id"]
                linker.receive_json()

            failed = client.get(f"/api/v1/discovery/sessions/{session_id}").json()
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["error"], "linker disconnected")

    def test_discovery_requires_auth_and_rejects_wrong_correlation(self) -> None:
        application = create_linker_app(ServerSettings(api_token="long-enough-token"))
        with TestClient(application) as client:
            body = {"linker_id": "linker.test", "timeout_s": 1}
            self.assertEqual(client.post("/api/v1/discovery/sessions", json=body).status_code, 401)
            with client.websocket_connect(
                "/api/v1/linkers/linker.test", headers={"Authorization": "Bearer long-enough-token"}
            ) as linker:
                linker.send_json(register_message())
                started = client.post(
                    "/api/v1/discovery/sessions",
                    json={**body, "timeout_s": 3},
                    headers={"Authorization": "Bearer long-enough-token"},
                )
                self.assertEqual(started.status_code, 202)
                session = started.json()
                start = linker.receive_json()
                linker.send_json(discovery_candidate(session["session_id"], str(uuid4())))
                with self.assertRaises(WebSocketDisconnect) as error:
                    linker.receive_json()
                self.assertEqual(error.exception.code, 1008)
                self.assertEqual(
                    client.get(
                        f"/api/v1/discovery/sessions/{session['session_id']}",
                        headers={"Authorization": "Bearer long-enough-token"},
                    ).json()["candidates"],
                    [],
                )

    def test_discovery_request_is_strictly_bounded(self) -> None:
        with TestClient(create_app(ServerSettings())) as client:
            for body in (
                {"linker_id": "linker.test", "timeout_s": 0},
                {"linker_id": "linker.test", "timeout_s": 61},
                {"linker_id": "linker.test", "timeout_s": 1, "device_id": "not-allowed"},
            ):
                self.assertEqual(client.post("/api/v1/discovery/sessions", json=body).status_code, 422)

    def test_admin_panel_is_optional_and_has_a_server_owned_path(self) -> None:
        application = create_app(ServerSettings())
        with TestClient(application) as client:
            response = client.get("/admin")
            if application.state.admin_panel_available:
                self.assertEqual(response.status_code, 200)
                self.assertIn("<html", response.text.lower())
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/auth").status_code, 200)
                self.assertEqual(client.get("/admin/unknown-page").status_code, 200)
                self.assertEqual(client.get("/auth/unknown-page").status_code, 200)
            else:
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["error"], "admin_panel_unavailable")
                self.assertEqual(client.get("/auth").status_code, 404)

    def test_invalid_brightness_is_rejected_and_disconnected_linker_is_not_success(self) -> None:
        with TestClient(create_linker_app()) as client:
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
            self.assertEqual(
                client.get("/api/v1/lights", headers={"Authorization": "Bearer long-enough-token"}).status_code,
                200,
            )
            admin = client.get("/admin")
            self.assertEqual(admin.status_code, 200 if application.state.admin_panel_available else 404)


if __name__ == "__main__":
    unittest.main()
