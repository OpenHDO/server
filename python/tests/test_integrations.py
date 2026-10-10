import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from openhdo_server.app import create_app
from openhdo_server.config import ServerSettings
from openhdo_server.integrations import IntegrationManager, IntegrationInput, DeviceAction, RoomInput
from openhdo_server.models import LightView, CommandResultEnvelope
from openhdo_server.service import ServiceError
from openhdo_server.tuya import signed_headers

CONFIG = dict(provider="tuya", name="Home", region="eu", access_id="access-id", secret="private-secret", uid="user-id")


class Cloud:
    def __init__(self):
        self.online = True
        self.failed = False
        self.empty = False
        self.commands = []
        self.power = False
        self.brightness = 500
        self.inventory_calls = 0

    def handle(self, request):
        expected = signed_headers(CONFIG["access_id"], CONFIG["secret"], request.method, request.url.raw_path.decode(), request.content, request.headers.get("access_token", ""), request.headers["t"])
        assert request.headers["sign"] == expected["sign"]
        if self.failed:
            return httpx.Response(200, json={"success": False, "code": 1106, "msg": "permission deny private-secret"})
        if request.url.path == "/v1.0/token":
            result = {"access_token": "cloud-token", "expire_time": 7200}
        elif request.url.path == "/v1.0/users/user-id/devices":
            self.inventory_calls += 1
            result = [] if self.empty else [{"id": "lamp-1", "name": "Lamp", "category": "dj", "online": self.online, "status": [{"code": "switch_led", "value": self.power}, {"code": "bright_value_v2", "value": self.brightness}, {"code": "colour_data_v2", "value": '{"h":0,"s":1000,"v":1000}'}]}]
        elif request.url.path.endswith(("/functions", "/specifications")):
            result = {"functions": [{"code": "switch_led", "type": "Boolean", "values": "{}"}, {"code": "bright_value_v2", "type": "Integer", "values": '{"min":10,"max":1000,"step":1,"scale":0}'}, {"code": "work_mode", "type": "Enum", "values": '{"range":["white","colour"]}'}, {"code": "colour_data_v2", "type": "Json", "values": json.dumps({key: {"min": 0, "max": 360 if key == "h" else 1000} for key in ("h", "s", "v")})}]}
        elif request.url.path.endswith("/commands"):
            self.commands.append(json.loads(request.content))
            for command in self.commands[-1]["commands"]:
                if command["code"] == "switch_led":
                    self.power = command["value"]
                if command["code"] == "bright_value_v2":
                    self.brightness = command["value"]
            result = True
        else:
            raise AssertionError(str(request.url))
        return httpx.Response(200, json={"success": True, "result": result})


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tuya_white_mode_preserves_rgb_channel_brightness(self):
        home = await self.manager.add(IntegrationInput(**CONFIG))
        device = self.manager.devices()[0]
        with self.manager.db:
            row = self.manager.db.execute('SELECT data FROM devices WHERE id=?',(device['id'],)).fetchone()
            data = json.loads(row['data'])
            data['state'].update(work_mode='colour',colour_data_v2={'h':240,'s':1000,'v':910})
            data['controls'].append({'code':'temp_value_v2','name':'White temperature','type':'Integer','constraints':{'min':0,'max':1000,'step':1}})
            self.manager.db.execute('UPDATE devices SET data=? WHERE id=?',(json.dumps(data),device['id']))
        from unittest.mock import AsyncMock
        send = AsyncMock()
        with patch.object(self.manager.tuya,'command',send):
            await self.manager.action(device['id'],DeviceAction(code='temp_value_v2',value=500))
        self.assertEqual(send.call_args.args[2:4],('temp_value_v2',500))
        self.assertEqual(send.call_args.args[4],[{'code':'work_mode','value':'white'},{'code':'bright_value_v2','value':910}])

    async def test_light_client_reports_active_color_brightness(self):
        from openhdo_server.lights import light_view
        await self.manager.add(IntegrationInput(**CONFIG))
        device = self.manager.devices()[0]
        device['state'].update(work_mode='colour',colour_data_v2={'h':240,'s':1000,'v':390},bright_value_v2=1000)
        self.assertEqual(light_view(device)['state']['brightness'],99)
        device['state']['work_mode']='white'
        self.assertEqual(light_view(device)['state']['brightness'],255)

    async def test_background_workers_are_independent_and_cancel_on_shutdown(self):
        started = asyncio.Event()
        workers, cancelled = set(), set()
        async def poll(integration_id):
            workers.add(integration_id)
            if len(workers) == 2:
                started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add(integration_id)
        with patch.object(self.manager, 'integrations', return_value=[{'id':'tuya'}, {'id':'yandex'}]), patch.object(self.manager, 'poll', poll):
            task = asyncio.create_task(self.manager.run())
            try:
                await asyncio.wait_for(started.wait(), 1)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(workers, {'tuya', 'yandex'})
        self.assertEqual(cancelled, workers)

    async def test_sync_reads_do_not_block_edits_and_busy_device_state_is_preserved(self):
        home = await self.manager.add(IntegrationInput(**CONFIG))
        device = self.manager.devices()[0]
        read_started, release = asyncio.Event(), asyncio.Event()
        stale = dict(device)
        stale['state'] = {**device['state'], 'switch_led': False}
        for key in ('id','integration_id','area','enabled','room_id','kind_override'):
            stale.pop(key, None)
        async def fetch(entry):
            read_started.set()
            await release.wait()
            return [stale]
        with patch.object(self.manager, 'fetch_devices', fetch):
            task = asyncio.create_task(self.manager.sync(home['id']))
            await asyncio.wait_for(read_started.wait(), 1)
            self.assertFalse(self.manager.lock.locked())
            await self.manager.save_room(RoomInput(name='Office',device_ids=[device['id']]))
            with self.manager.db:
                row = self.manager.db.execute('SELECT data FROM devices WHERE id=?',(device['id'],)).fetchone()
                data = json.loads(row['data'])
                data['state']['switch_led'] = True
                data['state_revision'] += 1
                self.manager.db.execute('UPDATE devices SET data=? WHERE id=?',(json.dumps(data),device['id']))
            release.set()
            await task
        self.assertTrue(self.manager.device(device['id'])['state']['switch_led'])
        self.assertEqual(self.manager.device(device['id'])['area'], 'Office')

    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "devices.sqlite3"
        self.cloud = Cloud()
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.cloud.handle)))

    async def asyncTearDown(self):
        await self.manager.close()
        self.directory.cleanup()

    async def test_signing_matches_documented_canonical_string(self):
        canonical = "clienttoken123GET\n" + hashlib.sha256(b"").hexdigest() + "\n\n/v1.0/devices/test"
        expected = hmac.new(b"secret", canonical.encode(), hashlib.sha256).hexdigest().upper()
        actual = signed_headers("client", "secret", "GET", "/v1.0/devices/test", b"", "token", "123")
        self.assertEqual(actual["sign"], expected)

    async def test_region_is_detected_without_user_selection_and_persisted(self):
        attempted = []
        def handle(request):
            attempted.append(request.url.host)
            if request.url.host != "openapi-ueaz.tuyaus.com":
                return httpx.Response(200, json={"success": False, "code": 1106})
            return self.cloud.handle(request)
        await self.manager.client.aclose()
        self.manager.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.manager.tuya.client = self.manager.client
        config = {key: value for key, value in CONFIG.items() if key != "region"}
        home = await self.manager.add(IntegrationInput(**config))
        self.assertEqual(home["region"], "us_east")
        self.assertEqual(len(set(attempted)), 6)
        attempted.clear()
        await self.manager.sync(home["id"])
        self.assertEqual(set(attempted), {"openapi-ueaz.tuyaus.com"})

    async def test_automatic_sync_refreshes_expired_function_definitions(self):
        home = await self.manager.add(IntegrationInput(**CONFIG))
        key = next(iter(self.manager.tuya.functions))
        functions, _ = self.manager.tuya.functions[key]
        self.manager.tuya.functions[key] = ({"functions": []}, 0)
        await self.manager.sync(home["id"])
        self.assertEqual(self.manager.tuya.functions[key][0], functions)
        self.assertTrue(any(control["code"] == "colour_data_v2" for control in self.manager.devices()[0]["controls"]))

    async def test_non_lighting_devices_import_and_control_without_rgb_flags(self):
        def handle(request):
            response = self.cloud.handle(request)
            if request.url.path == "/v1.0/users/user-id/devices":
                payload = response.json()
                payload["result"] = [{"id": "socket-1", "name": "Socket", "category": "cz", "online": True, "status": [{"code": "switch_1", "value": True}]}]
                return httpx.Response(200, json=payload)
            if request.url.path.endswith(("/functions", "/specifications")):
                return httpx.Response(200, json={"success": True, "result": {"functions": [{"code": "switch_1", "type": "Boolean", "values": "{}"}]}})
            return response
        await self.manager.client.aclose()
        self.manager.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.manager.tuya.client = self.manager.client
        await self.manager.add(IntegrationInput(**CONFIG))
        device = self.manager.devices()[0]
        self.assertEqual(device["kind"], "cz")
        self.assertEqual([c["code"] for c in device["controls"]], ["switch_1"])
        await self.manager.action(device["id"], DeviceAction(code="switch_1", value=False))
        self.assertEqual(self.cloud.commands[-1], {"commands": [{"code": "switch_1", "value": False}]})

    async def test_reported_measurement_specs_do_not_grant_control(self):
        def handle(request):
            if request.url.path.endswith("/specifications"):
                return httpx.Response(200, json={"success": True, "result": {"functions": [], "status": [{"code": "temp_current", "type": "Integer", "values": '{"min":-100,"max":600,"scale":1,"unit":"°C"}'}]}})
            return self.cloud.handle(request)
        await self.manager.client.aclose()
        self.manager.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.manager.tuya.client = self.manager.client
        await self.manager.add(IntegrationInput(**CONFIG))
        device = self.manager.devices()[0]
        self.assertEqual(device["status_specs"]["temp_current"]["scale"], 1)
        self.assertEqual(device["controls"], [])
        with self.assertRaises(ServiceError):
            await self.manager.action(device["id"], DeviceAction(code="temp_current", value=230))

    async def test_missing_specification_permission_falls_back_to_functions(self):
        def handle(request):
            if request.url.path.endswith("/specifications"):
                return httpx.Response(200, json={"success": False, "code": 1106})
            return self.cloud.handle(request)
        await self.manager.client.aclose()
        self.manager.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.manager.tuya.client = self.manager.client
        await self.manager.add(IntegrationInput(**CONFIG))
        device = self.manager.devices()[0]
        self.assertTrue(device["available"])
        self.assertTrue(device["controls"])
        self.assertEqual(device["status_specs"], {})

    async def test_import_persistence_stable_ids_and_local_metadata(self):
        home = await self.manager.add(IntegrationInput(**CONFIG))
        self.assertNotIn("secret", home)
        device = self.manager.devices()[0]
        with self.manager.db:
            self.manager.db.execute("UPDATE devices SET name='Desk',area='Office' WHERE id=?", (device["id"],))
        await self.manager.sync(home["id"])
        self.assertEqual(self.manager.devices()[0]["state_revision"], device["state_revision"])
        await self.manager.close()
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.cloud.handle)))
        restored = self.manager.devices()[0]
        self.assertEqual((restored["id"], restored["name"], restored["area"]), (device["id"], "Desk", "Office"))
        self.cloud.power = True
        await self.manager.sync(home["id"])
        self.assertGreater(self.manager.devices()[0]["state_revision"], device["state_revision"])

    async def test_rooms_move_rename_sync_restart_and_delete_without_devices_loss(self):
        home = await self.manager.add(IntegrationInput(**CONFIG))
        device_id = self.manager.devices()[0]["id"]
        office = await self.manager.save_room(RoomInput(name="Office", device_ids=[device_id]))
        living = await self.manager.save_room(RoomInput(name="Living room"))
        self.assertEqual(self.manager.device(device_id)["room_id"], office["id"])
        await self.manager.save_room(RoomInput(name="Living room", device_ids=[device_id]), living["id"])
        self.assertEqual(self.manager.room(office["id"])["device_count"], 0)
        await self.manager.save_room(RoomInput(name="Lounge", device_ids=[device_id]), living["id"])
        await self.manager.sync(home["id"])
        self.assertEqual(self.manager.device(device_id)["area"], "Lounge")
        await self.manager.close()
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.cloud.handle)))
        self.assertEqual(self.manager.device(device_id)["room_id"], living["id"])
        await self.manager.delete_room(living["id"])
        self.assertIsNone(self.manager.device(device_id)["room_id"])
        self.assertEqual(self.manager.device(device_id)["area"], "")

    async def test_room_validation_is_atomic_and_case_insensitive(self):
        await self.manager.add(IntegrationInput(**CONFIG))
        device_id = self.manager.devices()[0]["id"]
        room = await self.manager.save_room(RoomInput(name="Office", device_ids=[device_id]))
        for change in [RoomInput(name="office"), RoomInput(name="Other", device_ids=[device_id, "missing"]), RoomInput(name="Other", device_ids=[device_id, device_id])]:
            with self.assertRaises(ServiceError):
                await self.manager.save_room(change)
        self.assertEqual(self.manager.device(device_id)["room_id"], room["id"])
        self.assertEqual(len(self.manager.rooms()), 1)

    async def test_legacy_areas_migrate_to_rooms(self):
        await self.manager.add(IntegrationInput(**CONFIG))
        device_id = self.manager.devices()[0]["id"]
        with self.manager.db:
            self.manager.db.execute("UPDATE devices SET area='Office',room_id=NULL WHERE id=?", (device_id,))
            self.manager.db.execute("DROP INDEX IF EXISTS devices_room_idx")
            self.manager.db.execute("ALTER TABLE devices DROP COLUMN room_id")
        await self.manager.close()
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.cloud.handle)))
        self.assertEqual(self.manager.rooms()[0]["name"], "Office")
        self.assertEqual(self.manager.device(device_id)["room_id"], self.manager.rooms()[0]["id"])

    async def test_failed_sync_keeps_inventory_but_disables_control_and_recovers(self):
        home = await self.manager.add(IntegrationInput(**CONFIG))
        device_id = self.manager.devices()[0]["id"]
        self.cloud.failed = True
        with self.assertRaises(ServiceError):
            await self.manager.sync(home["id"])
        self.assertFalse(self.manager.device(device_id)["available"])
        self.assertNotIn("private-secret", self.manager.integrations()[0]["error"])
        with self.assertRaises(ServiceError):
            await self.manager.action(device_id, DeviceAction(code="switch_led", value=True))
        self.cloud.failed = False
        await self.manager.sync(home["id"])
        self.assertTrue(self.manager.device(device_id)["available"])

    async def test_actions_are_validated_against_real_functions(self):
        await self.manager.add(IntegrationInput(**CONFIG))
        device_id = self.manager.devices()[0]["id"]
        for code, value in [("switch_led", 1), ("bright_value_v2", 1001), ("work_mode", "invalid"), ("invented_dp", True), ("colour_data_v2", {"h": 361, "s": 0, "v": 0})]:
            with self.assertRaises(ServiceError):
                await self.manager.action(device_id, DeviceAction(code=code, value=value))
        self.assertEqual(self.cloud.commands, [])
        updated = await self.manager.action(device_id, DeviceAction(code="switch_led", value=True))
        self.assertTrue(updated["state"]["switch_led"])
        await self.manager.action(device_id, DeviceAction(code="colour_data_v2", value={"h": 120, "s": 1000, "v": 500}))
        self.assertEqual(len(self.cloud.commands), 2)

    async def test_no_phantom_devices_duplicate_accounts_and_reconciliation(self):
        self.cloud.empty = True
        home = await self.manager.add(IntegrationInput(**CONFIG))
        self.assertEqual(self.manager.devices(), [])
        with self.assertRaises(ServiceError):
            await self.manager.add(IntegrationInput(**CONFIG))
        self.cloud.empty = False
        await self.manager.sync(home["id"])
        self.assertEqual(len(self.manager.devices()), 1)
        self.cloud.empty = True
        await self.manager.sync(home["id"])
        self.assertEqual(self.manager.devices(), [])
        await self.manager.delete(home["id"])
        self.assertEqual(self.manager.integrations(), [])

    async def test_bad_credentials_do_not_create_an_integration(self):
        self.cloud.failed = True
        with self.assertRaises(ServiceError):
            await self.manager.add(IntegrationInput(**CONFIG))
        self.assertEqual(self.manager.integrations(), [])

    async def test_signed_post_uses_exact_utf8_body(self):
        body = '{"commands":[{"code":"switch_led","value":true}]}'.encode()
        canonical = "clienttoken123POST\n" + hashlib.sha256(body).hexdigest() + "\n\n/v1.0/devices/lamp/commands"
        expected = hmac.new(b"secret", canonical.encode(), hashlib.sha256).hexdigest().upper()
        self.assertEqual(signed_headers("client", "secret", "POST", "/v1.0/devices/lamp/commands", body, "token", "123")["sign"], expected)

    async def test_readback_failure_does_not_report_an_accepted_command_as_rejected(self):
        await self.manager.add(IntegrationInput(**CONFIG))
        device_id = self.manager.devices()[0]["id"]
        original = self.cloud.handle
        def fail_after_command(request):
            response = original(request)
            if request.url.path.endswith("/commands"):
                self.cloud.failed = True
            return response
        await self.manager.client.aclose()
        self.manager.client = httpx.AsyncClient(transport=httpx.MockTransport(fail_after_command))
        self.manager.tuya.client = self.manager.client
        result = await self.manager.action(device_id, DeviceAction(code="switch_led", value=True))
        self.assertFalse(result["available"])
        self.assertEqual(len(self.cloud.commands), 1)

    async def test_malformed_inventory_does_not_overwrite_existing_devices(self):
        home = await self.manager.add(IntegrationInput(**CONFIG))
        previous = self.manager.devices()[0]["state"]
        async def malformed(entry):
            return [{"external_id": "bad", "state": {}, "available": True}]
        self.manager.fetch_devices = malformed
        with self.assertRaises(ServiceError):
            await self.manager.sync(home["id"])
        self.assertEqual(len(self.manager.devices()), 1)
        self.assertEqual(self.manager.devices()[0]["state"], previous)


class IntegrationApiTests(unittest.TestCase):
    def test_room_api_membership_from_room_and_device_settings(self):
        with TestClient(self.app()) as client:
            self.assertEqual(client.get("/api/v1/rooms").status_code, 401)
            client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"})
            self.assertEqual(client.post("/api/v1/rooms", json={"name": "Office"}).status_code, 403)
            headers = {"X-OpenHDO-CSRF": client.cookies["openhdo_csrf"]}
            client.post("/api/v1/integrations", json=CONFIG, headers=headers)
            device = client.get("/api/v1/devices").json()["devices"][0]
            response = client.post("/api/v1/rooms", json={"name": "Office", "device_ids": [device["id"]]}, headers=headers)
            self.assertEqual(response.status_code, 201, response.text)
            office = response.json()
            living = client.post("/api/v1/rooms", json={"name": "Living room"}, headers=headers).json()
            updated = client.patch(f"/api/v1/devices/{device['id']}", json={"name": "Lamp", "room_id": living["id"], "enabled": True}, headers=headers)
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["area"], "Living room")
            failed = client.patch(f"/api/v1/devices/{device['id']}", json={"name": "Lamp", "room_id": "missing"}, headers=headers)
            self.assertEqual(failed.status_code, 404)
            self.assertEqual(client.get(f"/api/v1/devices/{device['id']}").json()["room_id"], living["id"])
            kept = client.patch(f"/api/v1/devices/{device['id']}", json={"name": "Desk lamp"}, headers=headers)
            self.assertEqual(kept.json()["room_id"], living["id"])
            response = client.put(f"/api/v1/rooms/{office['id']}", json={"name": "Study", "device_ids": [device["id"]]}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get(f"/api/v1/devices/{device['id']}").json()["area"], "Study")
            self.assertEqual(client.delete(f"/api/v1/rooms/{office['id']}", headers=headers).status_code, 204)
            self.assertIsNone(client.get(f"/api/v1/devices/{device['id']}").json()["room_id"])
            self.assertEqual(client.post("/api/v1/rooms", json={"name": "   "}, headers=headers).status_code, 422)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.settings = ServerSettings(data_dir=self.directory.name, auth_db_path=str(Path(self.directory.name) / "auth.sqlite3"), api_token="server-token", admin_username="admin", admin_password="admin-password")
        self.cloud = Cloud()

    def app(self):
        app = create_app(self.settings)
        asyncio.run(app.state.integrations.client.aclose())
        app.state.integrations.client = httpx.AsyncClient(transport=httpx.MockTransport(self.cloud.handle))
        app.state.integrations.tuya.client = app.state.integrations.client
        return app

    def tearDown(self):
        self.directory.cleanup()

    def test_api_crud_auth_csrf_and_light_compatibility(self):
        with TestClient(self.app()) as client:
            self.assertEqual(client.get("/api/v1/devices").status_code, 401)
            client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"})
            self.assertEqual(client.post("/api/v1/integrations", json=CONFIG).status_code, 403)
            headers = {"X-OpenHDO-CSRF": client.cookies["openhdo_csrf"]}
            added = client.post("/api/v1/integrations", json=CONFIG, headers=headers)
            self.assertEqual(added.status_code, 201, added.text)
            home_id = added.json()["id"]
            self.assertNotIn("private-secret", added.text)
            device = client.get("/api/v1/devices").json()["devices"][0]
            light = client.get("/api/v1/lights").json()["lights"][0]
            LightView.model_validate(light)
            command = {"power": True, "idempotency_key": "command-1"}
            first = client.patch(f"/api/v1/lights/{device['id']}", json=command, headers=headers)
            self.assertEqual(first.status_code, 202, first.text)
            CommandResultEnvelope.model_validate(first.json())
            second = client.patch(f"/api/v1/lights/{device['id']}", json=command, headers=headers)
            self.assertEqual(first.json(), second.json())
            self.assertEqual(len(self.cloud.commands), 1)
            conflict = client.patch(f"/api/v1/lights/{device['id']}", json={"power": False, "idempotency_key": "command-1"}, headers=headers)
            self.assertEqual(conflict.status_code, 409)
            updated = client.patch(f"/api/v1/devices/{device['id']}", json={"name": "Desk", "area": "Office", "enabled": False}, headers=headers)
            self.assertEqual(updated.status_code, 200)
            self.assertFalse(updated.json()["available"])
            self.assertEqual(client.post(f"/api/v1/devices/{device['id']}/actions", json={"code": "switch_led", "value": False}, headers=headers).status_code, 409)
            self.assertEqual(client.delete(f"/api/v1/integrations/{home_id}", headers=headers).status_code, 204)
            self.assertEqual(client.get("/api/v1/devices").json()["devices"], [])
            self.assertEqual(client.get("/api/v1/linkers").status_code, 404)

    def test_regular_user_can_control_but_cannot_manage_integrations(self):
        with TestClient(self.app()) as client:
            admin_headers = {"Authorization": "Bearer server-token"}
            self.assertEqual(client.post("/api/v1/integrations", json=CONFIG, headers=admin_headers).status_code, 201)
            device_id = client.get("/api/v1/devices", headers=admin_headers).json()["devices"][0]["id"]
            client.post("/api/v1/auth/register", json={"username": "user", "password": "user-password"})
            client.post("/api/v1/auth/login", json={"username": "user", "password": "user-password"})
            headers = {"X-OpenHDO-CSRF": client.cookies["openhdo_csrf"]}
            self.assertEqual(client.post("/api/v1/integrations", json=CONFIG, headers=headers).status_code, 403)
            self.assertEqual(client.get("/api/v1/rooms").status_code, 200)
            self.assertEqual(client.post("/api/v1/rooms", json={"name": "Office"}, headers=headers).status_code, 403)
            self.assertEqual(client.post(f"/api/v1/devices/{device_id}/actions", json={"code": "switch_led", "value": True}, headers=headers).status_code, 200)

    def test_validation_never_echoes_access_secret_and_rejects_other_providers(self):
        with TestClient(self.app()) as client:
            headers = {"Authorization": "Bearer server-token"}
            response = client.post("/api/v1/integrations", json={**CONFIG, "region": "wrong", "extra": "private-secret"}, headers=headers)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("private-secret", response.text)
            self.assertEqual(client.post("/api/v1/integrations", json={**CONFIG, "provider": "home_assistant"}, headers=headers).status_code, 422)

    def test_events_require_auth_and_support_session_cookies(self):
        from starlette.websockets import WebSocketDisconnect
        with TestClient(self.app()) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("/api/v1/events"):
                    pass
            client.post("/api/v1/integrations", json=CONFIG, headers={"Authorization": "Bearer server-token"})
            client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"})
            with client.websocket_connect("/api/v1/events") as socket:
                event = socket.receive_json()
                self.assertEqual(event["type"], "light.updated")
                LightView.model_validate(event["payload"])

    def test_devices_events_follow_external_power_and_availability_changes(self):
        with TestClient(self.app()) as client:
            headers = {'Authorization':'Bearer server-token'}
            home = client.post('/api/v1/integrations',json=CONFIG,headers=headers).json()
            client.post('/api/v1/auth/login',json={'username':'admin','password':'admin-password'})
            def devices_event(socket):
                while True:
                    event = socket.receive_json()
                    if event['type'] == 'devices.updated':
                        return event['payload']['devices']
            with client.websocket_connect('/api/v1/events?devices=1') as socket:
                initial = devices_event(socket)[0]
                self.assertFalse(initial['state']['switch_led'])
                self.cloud.power = True
                client.post('/api/v1/integrations/'+home['id']+'/sync',headers=headers).raise_for_status()
                changed = devices_event(socket)[0]
                self.assertTrue(changed['state']['switch_led'])
                self.assertGreater(changed['state_revision'],initial['state_revision'])
                self.cloud.online = False
                client.post('/api/v1/integrations/'+home['id']+'/sync',headers=headers).raise_for_status()
                self.assertFalse(devices_event(socket)[0]['available'])
                self.assertEqual(self.cloud.commands, [])

    def test_events_include_room_and_integration_updates_without_device_changes(self):
        with TestClient(self.app()) as client:
            headers = {'Authorization': 'Bearer server-token'}
            client.post('/api/v1/integrations', json=CONFIG, headers=headers).raise_for_status()
            client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin-password'})
            def event(socket):
                while True:
                    message = socket.receive_json()
                    if message['type'] == 'devices.updated':
                        return message['payload']
            with client.websocket_connect('/api/v1/events?devices=1') as socket:
                initial = event(socket)
                self.assertEqual(len(initial['integrations']), 1)
                self.assertEqual(initial['rooms'], [])
                client.post('/api/v1/rooms', json={'name': 'Empty room'}, headers=headers).raise_for_status()
                changed = event(socket)
                self.assertEqual(changed['rooms'][0]['name'], 'Empty room')
                self.assertEqual(initial['devices'], changed['devices'])

    def test_reconfigure_preserves_ids_and_local_names_and_failed_validation(self):
        with TestClient(self.app()) as client:
            headers = {"Authorization": "Bearer server-token"}
            home = client.post("/api/v1/integrations", json=CONFIG, headers=headers).json()
            device = client.get("/api/v1/devices", headers=headers).json()["devices"][0]
            client.patch(f"/api/v1/devices/{device['id']}", headers=headers, json={"name": "Desk", "area": "Office", "enabled": True})
            response = client.put(f"/api/v1/integrations/{home['id']}", headers=headers, json={**CONFIG, "name": "Renamed"})
            self.assertEqual(response.status_code, 200, response.text)
            restored = client.get("/api/v1/devices", headers=headers).json()["devices"][0]
            self.assertEqual((restored["id"], restored["name"], restored["area"]), (device["id"], "Desk", "Office"))
            self.cloud.failed = True
            response = client.put(f"/api/v1/integrations/{home['id']}", headers=headers, json={**CONFIG, "name": "Not saved"})
            self.assertEqual(response.status_code, 502)
            self.assertEqual(client.get("/api/v1/integrations", headers=headers).json()["integrations"][0]["name"], "Renamed")

    def test_cors_allows_reconfiguration_without_weakening_auth(self):
        self.settings = self.settings.model_copy(update={"cors_origins": ("http://localhost:5173",)})
        with TestClient(self.app()) as client:
            response = client.options("/api/v1/integrations/example", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "Authorization,Content-Type"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get("/api/v1/devices", headers={"Origin": "http://localhost:5173"}).status_code, 401)

    def test_restarted_server_deduplicates_light_commands(self):
        headers = {"Authorization": "Bearer server-token"}
        with TestClient(self.app()) as client:
            client.post("/api/v1/integrations", json=CONFIG, headers=headers)
            device_id = client.get("/api/v1/devices", headers=headers).json()["devices"][0]["id"]
            body = {"brightness": 255, "idempotency_key": "persisted-command"}
            first = client.patch(f"/api/v1/lights/{device_id}", json=body, headers=headers)
            self.assertEqual(first.status_code, 202)
            self.assertEqual(self.cloud.brightness, 1000)
        with TestClient(self.app()) as client:
            second = client.patch(f"/api/v1/lights/{device_id}", json=body, headers=headers)
            self.assertEqual(first.json(), second.json())
            self.assertEqual(len(self.cloud.commands), 1)
