import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from urllib.parse import parse_qs
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from openhdo_server.app import create_app
from openhdo_server.config import ServerSettings
from openhdo_server.integrations import IntegrationManager, YandexLoginInput, DeviceAction, RoomInput
from openhdo_server.service import ServiceError
import importlib.util
import sys
import shutil
from openhdo_plugin import PluginContext
from openhdo_server.plugins import PluginManager, ManagedProvider
from openhdo_server.integrations import YandexLoginView
PLUGIN_ROOT = Path(__file__).resolve().parents[3] / 'server-yandex'
if not (PLUGIN_ROOT / 'backend/plugin.py').is_file():
    raise unittest.SkipTest('Optional Yandex integration tests require the sibling server-yandex plugin checkout')
spec = importlib.util.spec_from_file_location('_test_yandex', PLUGIN_ROOT / 'backend/plugin.py', submodule_search_locations=[str(PLUGIN_ROOT / 'backend')])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
YandexAccount, snapshot, DEVICE_TYPES = plugin.YandexAccount, sys.modules['_test_yandex.yandex'].snapshot, sys.modules['_test_yandex.yandex'].DEVICE_TYPES

CONFIG = {"client_id": "public-id", "client_secret": "shared-secret"}


class Cloud:
    def __init__(self):
        self.confirmed = False
        self.accepted = True
        self.error_code = None
        self.online = True
        self.fail_detail = False
        self.fail_reads = False
        self.uid = "account-1"
        self.power = False
        self.calls = []
        self.commands = []
        self.device = {"id": "socket-1", "name": "Socket", "type": "devices.types.socket",
            "capabilities": [{"type": "devices.capabilities.on_off", "parameters": {"split": False},
                "state": {"instance": "on", "value": False}}],
            "properties": [{"type": "devices.properties.float", "parameters": {"instance": "power", "unit": "unit.watt"},
                "state": {"instance": "power", "value": 12.5}}]}

    def transport(self, request):
        self.calls.append(request)
        if request.url.host == "oauth.yandex.ru":
            form = parse_qs(request.content.decode())
            if request.url.path == "/device/code":
                assert form["scope"] == ["iot:view iot:control"]
                return httpx.Response(200, json={"device_code": "private-device-code", "user_code": "ABCD-EFGH",
                    "verification_url": "https://ya.ru/device", "expires_in": 300, "interval": 5})
            if form["grant_type"] == ["device_code"] and not self.confirmed:
                return httpx.Response(400, json={"error": "authorization_pending"})
            assert form["client_secret"] == ["shared-secret"]
            renewed = form["grant_type"] == ["refresh_token"]
            return httpx.Response(200, json={"access_token": "private-access-new" if renewed else "private-access",
                "refresh_token": "private-refresh-new" if renewed else "private-refresh", "expires_in": 3600})
        if request.url.host == "login.yandex.ru":
            return httpx.Response(200, json={"id": self.uid})
        if request.url.path.endswith("user/info"):
            if self.fail_reads:
                return httpx.Response(503, json={"detail": "private-access"})
            self.device["capabilities"][0]["state"]["value"] = self.power
            return httpx.Response(200, json={"status": "ok", "devices": [self.device]})
        if request.url.path.startswith('/v1.0/devices/') and request.method == 'GET':
            if self.fail_detail:
                return httpx.Response(503,json={'status':'error'})
            device = json.loads(json.dumps(self.device))
            for capability in device.get('capabilities', []):
                if capability['type'] == 'devices.capabilities.on_off':
                    capability['state']['value'] = self.power
            return httpx.Response(200,json={'status':'ok',**device,'state':'online' if self.online else 'offline'})
        if request.url.path.endswith("devices/actions"):
            command = json.loads(request.content)["devices"][0]
            self.commands.append(command)
            capability = command["actions"][0]
            if capability['type'] == 'devices.capabilities.on_off' and self.accepted:
                self.power = capability['state']['value']
            return httpx.Response(200, json={"status": "ok", "devices": [{"id": command["id"], "capabilities": [{
                "type": action["type"], "state": {"instance": action["state"]["instance"],
                    "action_result": {"status": "DONE" if self.accepted else "ERROR", "error_code": self.error_code}}} for action in command['actions']]}]})
        raise AssertionError(str(request.url))


class YandexTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "devices" / "integrations.sqlite3"
        self.cloud = Cloud()
        self.route = self.cloud.transport
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.route)))
        self.setup_provider()

    def setup_provider(self):
        manifest = json.loads((PLUGIN_ROOT / 'hdo.json').read_text(encoding='utf-8'))
        self.context = PluginContext(manifest, Path(self.directory.name) / 'plugin-data', {'devices': self.manager, 'http': self.manager.client}, None)
        self.provider = plugin.YandexProvider(self.context)
        self.provider.save_settings(CONFIG)
        self.plugins = PluginManager(self.directory.name)
        self.plugins.contexts[manifest['id']] = self.context
        self.plugins.records[manifest['id']] = {'status': 'enabled'}
        self.manager.plugin_providers[plugin.PROVIDER] = ManagedProvider(self.plugins, manifest['id'], self.provider)

    async def start(self, change, owner):
        return YandexLoginView.model_validate(await self.provider.start_yandex_login(change, owner))

    async def asyncTearDown(self):
        await self.context.close()
        await self.manager.close()
        self.directory.cleanup()

    async def connect(self, integration_id=None):
        login = await self.start(YandexLoginInput(integration_id=integration_id), "owner")
        self.cloud.confirmed = True
        result = await self.provider.check_yandex_login(login.id, "owner")
        return result["integration_id"], login.id

    async def test_legacy_migration_preserves_devices_and_rooms_without_reusing_tokens(self):
        integration_id, _ = await self.connect()
        device = self.manager.devices()[0]
        room = await self.manager.save_room(RoomInput(name='Living room', device_ids=[device['id']]))
        legacy = {'access_token': 'old-shared-token', 'refresh_token': 'old-refresh-token'}
        with self.manager.db:
            self.manager.db.execute("UPDATE integrations SET provider='yandex',auth_method='yandex',uid=?,secret=? WHERE id=?",
                                    ('account-1', json.dumps(legacy), integration_id))
            self.manager.db.execute('UPDATE devices SET name=? WHERE id=?', ('My socket', device['id']))
        manifest = json.loads((PLUGIN_ROOT / 'hdo.json').read_text(encoding='utf-8'))
        migrated = PluginContext(manifest, Path(self.directory.name) / 'migration', {'devices': self.manager, 'http': self.manager.client}, None)
        try:
            await plugin.activate(migrated)
            entry = self.manager.entry(integration_id)
            self.assertEqual(entry['provider'], plugin.PROVIDER)
            self.assertEqual(json.loads(entry['secret']), {'account_id': 'account-1'})
            self.assertEqual(json.loads(migrated.store.get('legacy:' + integration_id)['secret']), legacy)
            self.assertIsNone(migrated.store.get('account:account-1'))
            self.assertEqual(self.manager.device(device['id'])['room_id'], room['id'])
            self.assertEqual(self.manager.device(device['id'])['name'], 'My socket')
            self.assertEqual(migrated.store.get('oauth', {}), {})
        finally:
            await migrated.close()

    async def test_plugin_events_include_external_state_changes(self):
        integration_id, _ = await self.connect()
        received = []
        async def receive(kind, payload):
            received.append((kind, payload))
        self.manager.plugin_events = receive
        self.cloud.power = True
        await self.manager.sync(integration_id)
        self.assertTrue(next(payload for kind, payload in received if kind == 'device.changed')['state']['switch'])
        received.clear()
        await self.manager.sync(integration_id)
        self.assertFalse(any(kind == 'device.changed' for kind, _ in received))

    async def test_detail_state_overrides_cached_inventory_and_recovers(self):
        integration_id, _ = await self.connect()
        self.cloud.online = False
        await self.manager.sync(integration_id)
        self.assertFalse(self.manager.devices()[0]['available'])
        self.cloud.online = True
        self.cloud.power = True
        await self.manager.sync(integration_id)
        self.assertTrue(self.manager.devices()[0]['available'])
        self.assertTrue(self.manager.devices()[0]['state']['switch'])
        self.cloud.fail_detail = True
        await self.manager.sync(integration_id)
        self.assertTrue(self.manager.devices()[0]['available'])
        self.assertTrue(self.manager.devices()[0]['state_stale'])
        before = len(self.cloud.calls)
        await self.manager.sync(integration_id)
        self.assertEqual(len(self.cloud.calls), before)
        for key, (_, view) in self.provider.account.state_cache.items():
            self.provider.account.state_cache[key] = (time.monotonic() - 61, view)
        await self.manager.sync(integration_id)
        self.assertFalse(self.manager.devices()[0]['available'])
        self.assertTrue(self.manager.devices()[0]['state_stale'])
        self.cloud.fail_detail = False
        self.provider.account.state_retry.clear()
        await self.manager.sync(integration_id)
        self.assertTrue(self.manager.devices()[0]['available'])
        self.assertFalse(self.manager.devices()[0]['state_stale'])

    async def test_current_power_comes_from_detail_instead_of_inventory(self):
        integration_id, _ = await self.connect()
        original = self.manager.client._transport
        def route(request):
            response = self.cloud.transport(request)
            if request.url.path.startswith('/v1.0/devices/') and request.method == 'GET':
                device = response.json()
                device['capabilities'][0]['state']['value'] = True
                return httpx.Response(200, json=device)
            return response
        self.manager.client._transport = httpx.MockTransport(route)
        try:
            await self.manager.sync(integration_id)
            self.assertFalse(self.cloud.power)
            self.assertTrue(self.manager.devices()[0]['state']['switch'])
        finally:
            self.manager.client._transport = original

    async def test_failed_detail_does_not_hide_other_devices(self):
        integration_id, _ = await self.connect()
        self.provider.account.inventory_cache.clear()
        original = self.manager.client._transport
        def route(request):
            if request.url.path == '/v1.0/devices/socket-2':
                return httpx.Response(503, json={'status': 'error'})
            response = self.cloud.transport(request)
            if request.url.path.endswith('user/info'):
                data = response.json()
                data['devices'].append({**data['devices'][0], 'id': 'socket-2'})
                return httpx.Response(200, json=data)
            return response
        self.manager.client._transport = httpx.MockTransport(route)
        try:
            await self.manager.sync(integration_id)
            devices = {device['external_id']: device for device in self.manager.devices()}
            self.assertTrue(devices['socket-1']['available'])
            self.assertFalse(devices['socket-2']['available'])
        finally:
            self.manager.client._transport = original

    async def test_inventory_is_cached_but_device_state_is_read_each_cycle(self):
        integration_id, _ = await self.connect()
        before = len(self.cloud.calls)
        self.cloud.power = True
        await self.manager.sync(integration_id)
        self.assertEqual([request.url.path for request in self.cloud.calls[before:]], ['/v1.0/devices/socket-1'])
        self.assertTrue(self.manager.devices()[0]['state']['switch'])

    async def test_rate_limit_stops_requests_and_does_not_retry_commands(self):
        calls = []
        def route(request):
            calls.append(request)
            return httpx.Response(429, headers={'Retry-After': '120'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
            account = YandexAccount(client, CONFIG)
            for method in ('GET', 'POST'):
                with self.assertRaises(ServiceError) as caught:
                    await account.request(method, 'https://api.iot.yandex.net/v1.0/devices/actions')
                self.assertEqual(caught.exception.code, 'yandex_rate_limited')
            self.assertEqual(len(calls), 1)
            self.assertGreater(account.retry_at[None], time.monotonic() + 119)
            with self.assertRaises(ServiceError):
                await account.request('GET', 'https://api.iot.yandex.net/v1.0/user/info', account_id='other-account')
            self.assertEqual(len(calls), 2)

    async def test_revoked_authentication_is_not_hidden_by_state_cache(self):
        integration_id, _ = await self.connect()
        original = self.manager.client._transport
        self.manager.client._transport = httpx.MockTransport(lambda request: httpx.Response(401))
        try:
            with self.assertRaises(ServiceError) as caught:
                await self.manager.sync(integration_id)
            self.assertEqual(caught.exception.code, 'yandex_login_expired')
        finally:
            self.manager.client._transport = original

    async def test_relative_range_commands_are_not_reported_as_absolute_state(self):
        self.cloud.device['type'] = 'devices.types.media_device.tv'
        self.cloud.device['capabilities'] = [{'type': 'devices.capabilities.range', 'parameters': {'instance': 'volume', 'random_access': False}, 'state': {'instance': 'volume', 'value': None}}]
        await self.connect()
        device = self.manager.devices()[0]
        result = await self.manager.action(device['id'], DeviceAction(code='range_volume', value=-1))
        self.assertTrue(self.cloud.commands[-1]['actions'][0]['state']['relative'])
        self.assertEqual(self.cloud.commands[-1]['actions'][0]['state']['value'], -1)
        self.assertNotIn('range_volume', result['state'])

    async def test_camera_stream_command_returns_validated_url(self):
        self.cloud.device['type'] = 'devices.types.camera'
        self.cloud.device['capabilities'] = [{'type': 'devices.capabilities.video_stream', 'retrievable': False, 'parameters': {'protocols': ['hls']}, 'state': {'instance': 'get_stream'}}]
        await self.connect()
        original = self.manager.client._transport
        def route(request):
            response = self.cloud.transport(request)
            if request.method == 'POST' and request.url.path.endswith('/devices/actions'):
                data = response.json()
                data['devices'][0]['capabilities'][0]['state']['value'] = {'protocol': 'hls', 'stream_url': 'https://camera.example/live.m3u8'}
                return httpx.Response(200, json=data)
            return response
        self.manager.client._transport = httpx.MockTransport(route)
        try:
            result = await self.manager.action(self.manager.devices()[0]['id'], DeviceAction(code='video_stream', value='hls'))
            self.assertEqual(result['state']['video_stream'], 'https://camera.example/live.m3u8')
            self.assertEqual(self.cloud.commands[-1]['actions'][0]['state']['value'], {'protocols': ['hls']})
        finally:
            self.manager.client._transport = original

    async def test_all_catalog_types_are_preserved_and_default_ranges_work(self):
        from openhdo_server.integrations import DeviceSnapshot
        asset_root = Path(__file__).resolve().parents[2] / 'web/public/devices/yandex'
        self.assertEqual(len(DEVICE_TYPES), 54)
        for kind, entry in DEVICE_TYPES.items():
            with self.subTest(kind=kind):
                view = snapshot({'id': kind, 'name': kind, 'type': 'devices.types.' + kind, 'state': 'online'})
                DeviceSnapshot.model_validate(view)
                self.assertEqual(view['device_type'], kind)
                self.assertTrue((asset_root / entry['on']).is_file())
                self.assertTrue((asset_root / entry['off']).is_file())
        view = snapshot({'id': 'light', 'name': 'light', 'type': 'devices.types.light', 'capabilities': [{'type': 'devices.capabilities.range', 'parameters': {'instance': 'brightness'}}]})
        self.assertEqual(view['controls'][0]['constraints']['max'], 100)
        self.assertEqual(view['controls'][0]['constraints']['step'], 1)

    async def test_local_device_flow_owner_and_poll_interval(self):
        login = await self.start(YandexLoginInput(), "owner")
        with self.assertRaises(ServiceError) as caught:
            await self.provider.check_yandex_login(login.id, "other")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(await self.provider.check_yandex_login(login.id, "owner"), {"status": "pending"})
        before = len(self.cloud.calls)
        self.assertEqual(await self.provider.check_yandex_login(login.id, "owner"), {"status": "pending"})
        self.assertEqual(len(self.cloud.calls), before)
        self.assertNotIn("private-device-code", login.model_dump_json())
        self.assertEqual({request.url.host for request in self.cloud.calls}, {"oauth.yandex.ru"})
        self.cloud.confirmed = True
        self.provider.logins[login.id]["session"]["next_poll"] = 0
        result = await self.provider.check_yandex_login(login.id, "owner")
        self.assertEqual(result["status"], "connected")
        self.assertEqual(self.provider.logins[login.id]["session"], {})

    async def test_local_login_privacy_commands_and_duplicate_account(self):
        integration_id, login_id = await self.connect()
        public = json.dumps(self.manager.integrations()) + json.dumps(self.manager.devices())
        self.assertNotIn("private", public)
        self.assertNotIn("shared-secret", public)
        self.assertEqual((await self.provider.check_yandex_login(login_id, "owner"))["integration_id"], integration_id)
        with self.assertRaises(ServiceError) as caught:
            await self.provider.check_yandex_login(login_id, "other")
        self.assertEqual(caught.exception.status_code, 404)
        device = self.manager.devices()[0]
        await self.manager.action(device["id"], DeviceAction(code="switch", value=True))
        self.assertTrue(self.manager.device(device["id"])["state"]["switch"])
        self.cloud.accepted = False
        with self.assertRaises(ServiceError):
            await self.manager.action(device["id"], DeviceAction(code="switch", value=False))
        with self.assertRaises(ServiceError):
            await self.connect()
        self.assertEqual(len(self.manager.integrations()), 1)

    async def test_direct_refresh_persists_on_failed_read(self):
        integration_id, _ = await self.connect()
        credentials = self.context.store.get('account:account-1')
        credentials['expires_at'] = 1
        self.context.store.set('account:account-1', credentials)
        self.cloud.fail_reads = True
        self.provider.account.inventory_cache.clear()
        with self.assertRaises(ServiceError):
            await self.manager.sync(integration_id)
        saved = self.context.store.get("account:account-1")
        self.assertEqual(saved["refresh_token"], "private-refresh-new")
        self.assertNotIn("broker_ticket", saved)
        self.assertEqual(len(self.manager.devices()), 1)
        self.assertFalse(self.manager.devices()[0]["available"])

    async def test_restart_reconnect_preserves_local_metadata_and_expiry(self):
        integration_id, login_id = await self.connect()
        device = self.manager.devices()[0]
        room = await self.manager.save_room(RoomInput(name="Study", device_ids=[device["id"]]))
        with self.manager.db:
            self.manager.db.execute("UPDATE devices SET name='Desk' WHERE id=?", (device["id"],))
        await self.context.close()
        await self.manager.close()
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.route)))
        self.setup_provider()
        await self.manager.sync(integration_id)
        await self.connect(integration_id)
        restored = self.manager.devices()[0]
        self.assertEqual((restored["id"], restored["name"], restored["room_id"]), (device["id"], "Desk", room["id"]))
        self.cloud.uid = "other"
        with self.assertRaises(ServiceError) as caught:
            await self.connect(integration_id)
        self.assertEqual(caught.exception.code, "account_mismatch")
        login = await self.start(YandexLoginInput(), "owner")
        self.provider.logins[login.id]["expires"] = 0
        with self.assertRaises(ServiceError) as caught:
            await self.provider.check_yandex_login(login.id, "owner")
        self.assertEqual(caught.exception.status_code, 410)

    def test_capabilities_decimal_ranges_rgb_and_properties(self):
        device = {"id": "lamp", "name": "Lamp", "type": "devices.types.light", "capabilities": [
            {"type": "devices.capabilities.color_setting", "parameters": {"color_model": "rgb", "temperature_k": {"min": 1700, "max": 6500}}, "state": {"instance": "rgb", "value": 0xFF0000}},
            {"type": "devices.capabilities.range", "parameters": {"instance": "temperature", "random_access": True, "unit": "unit.temperature.celsius", "range": {"min": 16, "max": 30, "precision": 0.5}}, "state": {"instance": "temperature", "value": 20.5}},
            {"type": "devices.capabilities.video_stream", "parameters": {}, "state": {}},
            {"type": "devices.capabilities.mode", "parameters": {"instance": "fan_speed", "modes": [{"value": "low"}, {"value": "high"}]}, "state": {"instance": "fan_speed", "value": "low"}}],
            "properties": [{"type": "devices.properties.event", "parameters": {"instance": "motion"}, "state": {"instance": "motion", "value": "unknown"}}]}
        value = snapshot(device)
        self.assertEqual(value["state"]["temp_set"], 205)
        self.assertEqual(value["state"]["colour_data_v2"], {"h": 0, "s": 1000, "v": 1000})
        self.assertEqual(value["state"]["pir"], "unknown")
        controls = {control["code"]: control for control in value["controls"]}
        self.assertEqual(controls["temp_set"]["constraints"]["step"], 5)
        self.assertEqual(controls["temp_value"]["constraints"]["unit"], "K")
        self.assertEqual(len(controls), 4)
        self.assertNotIn("temp_value", value["state"])

    async def test_rgb_and_decimal_commands_use_native_values_without_retries(self):
        integration_id, _ = await self.connect()
        entry = self.provider.entry(json.loads(self.manager.entry(integration_id)["secret"]))
        color = snapshot({"id": "lamp", "name": "Lamp", "type": "devices.types.light", "capabilities": [
            {"type": "devices.capabilities.color_setting", "parameters": {"color_model": "rgb"}, "state": {"instance": "rgb", "value": 0}}]})["controls"][0]
        await self.provider.account.command(entry, self.provider.persist, "lamp", color, {"h": 120, "s": 1000, "v": 1000})
        self.assertEqual(self.cloud.commands[-1]["actions"][0]["state"], {"instance": "rgb", "value": 0x00FF00})
        numeric = {"type": "Integer", "constraints": {"yandex_type": "devices.capabilities.range", "yandex_instance": "temperature", "scale": 1}}
        await self.provider.account.command(entry, self.provider.persist, "thermostat", numeric, 205)
        self.assertEqual(self.cloud.commands[-1]["actions"][0]["state"]["value"], 20.5)
        self.cloud.accepted = False
        count = len(self.cloud.commands)
        with self.assertRaises(ServiceError):
            await self.provider.account.command(entry, self.provider.persist, "thermostat", numeric, 210)
        self.assertEqual(len(self.cloud.commands), count + 1)
        self.cloud.device["capabilities"] = [{"type": "devices.capabilities.range", "parameters": {
            "instance": "temperature", "random_access": True, "range": {"min": "bad", "max": 30, "precision": 0.5}}}]
        with self.assertRaises(ServiceError) as caught:
            await self.manager.sync(integration_id)
        self.assertEqual(caught.exception.code, "invalid_inventory")
        self.assertEqual(len(self.manager.devices()), 1)

    async def test_light_subtypes_hsv_white_temperature_and_scenes(self):
        integration_id, _ = await self.connect()
        native = {"id": "strip", "name": "Strip", "type": "devices.types.light.strip", "capabilities": [
            {"type": "devices.capabilities.on_off", "state": {"instance": "on", "value": True}},
            {"type": "devices.capabilities.range", "parameters": {"instance": "brightness", "random_access": True,
                "range": {"min": 1, "max": 100, "precision": 1}}, "state": {"instance": "brightness", "value": 39}},
            {"type": "devices.capabilities.color_setting", "parameters": {"color_model": "hsv",
                "temperature_k": {"min": 2700, "max": 6500}, "color_scene": {"scenes": [{"id": "party"}, {"id": "reading"}]}},
                "state": {"instance": "hsv", "value": {"h": 120, "s": 96, "v": 39}}}]}
        device = snapshot(native)
        self.assertEqual(device["kind"], "dj")
        self.assertEqual(device["state"]["work_mode"], "colour")
        self.assertEqual(device["state"]["colour_data_v2"], {"h": 120, "s": 96, "v": 39})
        controls = {control["code"]: control for control in device["controls"]}
        self.assertEqual(set(controls), {"switch_led", "bright_value", "colour_data_v2", "temp_value", "color_scene"})
        self.assertEqual(controls["colour_data_v2"]["constraints"]["s"]["max"], 100)
        self.assertNotIn("temp_value", device["state"])
        entry = self.provider.entry(json.loads(self.manager.entry(integration_id)["secret"]))
        await self.provider.account.command(entry, self.provider.persist, "strip", controls["colour_data_v2"], {"h": 240, "s": 100, "v": 39})
        self.assertEqual(self.cloud.commands[-1]["actions"][0]["state"], {"instance": "hsv", "value": {"h": 240, "s": 100, "v": 39}})
        await self.provider.account.command(entry, self.provider.persist, "strip", controls["color_scene"], "party")
        self.assertEqual(self.cloud.commands[-1]["actions"][0]["state"], {"instance": "scene", "value": "party"})
        native["capabilities"][2]["state"] = {"instance": "temperature_k", "value": 3000}
        white = snapshot(native)
        self.assertEqual(white["state"]["work_mode"], "white")
        self.assertEqual(white["state"]["temp_value"], 3000)
        self.assertNotIn("colour_data_v2", white["state"])
        self.assertIn("colour_data_v2", {control["code"] for control in white["controls"]})

    def test_hierarchical_types_and_offline_state(self):
        for native, expected in (("light.lamp", "dj"), ("light.strip", "dj"), ("light.garland", "dj"),
            ("smart_speaker.yandex.station.micro", "speaker"), ("socket.power_strip", "cz"),
            ("thermostat.ac", "wk"), ("sensor.motion", "pir"), ("light_unknown", "device")):
            with self.subTest(native=native):
                device = snapshot({"id": "test", "name": "Test", "type": "devices.types." + native, "state": "offline"})
                self.assertEqual(device["kind"], expected)
                self.assertFalse(device["available"])

    async def test_command_acknowledgement_does_not_wait_for_inventory(self):
        await self.connect()
        device = self.manager.devices()[0]
        self.cloud.fail_reads = True
        before = len(self.cloud.calls)
        result = await self.manager.action(device['id'], DeviceAction(code='switch', value=True))
        self.assertTrue(result['state']['switch'])
        self.assertTrue(result['available'])
        self.assertEqual([request.url.path for request in self.cloud.calls[before:]], ['/v1.0/devices/actions'])

    async def test_white_temperature_preserves_color_brightness_in_one_request(self):
        integration_id, _ = await self.connect()
        native = {'id':'socket-1','name':'Lamp','type':'devices.types.light.lamp','capabilities':[
            {'type':'devices.capabilities.on_off','state':{'instance':'on','value':True}},
            {'type':'devices.capabilities.range','parameters':{'instance':'brightness','random_access':True,
                'range':{'min':1,'max':100,'precision':10}},'state':{'instance':'brightness','value':1}},
            {'type':'devices.capabilities.color_setting','parameters':{'color_model':'hsv','temperature_k':{'min':1000,'max':10000}},
                'state':{'instance':'hsv','value':{'h':240,'s':100,'v':91}}}]}
        await self.manager.sync_entry(self.manager.entry(integration_id), [snapshot(native)])
        device=self.manager.devices()[0]
        result=await self.manager.action(device['id'],DeviceAction(code='temp_value',value=4500))
        actions=self.cloud.commands[-1]['actions']
        self.assertEqual([action['state'] for action in actions], [{'instance':'brightness','value':90}, {'instance':'temperature_k','value':4500}])
        self.assertEqual(result['state']['work_mode'],'white')
        self.assertEqual(result['state']['bright_value'],90)
        result=await self.manager.action(device['id'],DeviceAction(code='bright_value',value=100))
        self.assertEqual(result['state']['bright_value'],100)
        self.assertEqual(result['state']['work_mode'],'white')
        with self.assertRaises(ServiceError):
            await self.manager.action(device['id'],DeviceAction(code='bright_value',value=99))

    async def test_brightness_command_keeps_color_mode(self):
        integration_id, _ = await self.connect()
        native={'id':'socket-1','name':'Lamp','type':'devices.types.light','capabilities':[
            {'type':'devices.capabilities.range','parameters':{'instance':'brightness','random_access':True,'range':{'min':1,'max':100,'precision':1}},'state':{'instance':'brightness','value':40}},
            {'type':'devices.capabilities.color_setting','parameters':{'color_model':'hsv'},'state':{'instance':'hsv','value':{'h':120,'s':100,'v':40}}}]}
        await self.manager.sync_entry(self.manager.entry(integration_id),[snapshot(native)])
        result=await self.manager.action(self.manager.devices()[0]['id'],DeviceAction(code='bright_value',value=50))
        self.assertEqual(result['state']['work_mode'],'colour')

    async def test_commands_on_different_devices_run_concurrently(self):
        integration_id, _ = await self.connect()
        other = {**self.cloud.device, 'id': 'socket-2'}
        await self.manager.sync_entry(self.manager.entry(integration_id), [snapshot(self.cloud.device), snapshot(other)])
        devices = self.manager.devices()
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def command(*args):
            calls.append(args[2])
            if len(calls) == 2:
                started.set()
            await release.wait()
        with patch.object(self.provider.account, 'command', command):
            async with self.manager.lock:
                tasks = [asyncio.create_task(self.manager.action(device['id'], DeviceAction(code='switch', value=True))) for device in devices]
                try:
                    await asyncio.wait_for(started.wait(), 1)
                finally:
                    release.set()
                    await asyncio.gather(*tasks)
        self.assertEqual(set(calls), {'socket-1', 'socket-2'})

    async def test_offline_command_marks_only_that_device(self):
        integration_id, _ = await self.connect()
        device = self.manager.devices()[0]
        self.cloud.accepted = False
        self.cloud.error_code = 'DEVICE_UNREACHABLE'
        with self.assertRaises(ServiceError) as caught:
            await self.manager.action(device['id'], DeviceAction(code='switch', value=True))
        self.assertEqual(caught.exception.code, 'yandex_device_unavailable')
        self.assertFalse(self.manager.device(device['id'])['available'])
        self.assertEqual(self.manager.entry(integration_id)['status'], 'connected')
        await self.manager.sync(integration_id)
        self.assertTrue(self.manager.device(device['id'])['available'])

    async def test_local_socket_type_survives_sync_with_garland_icon(self):
        integration_id, _ = await self.connect()
        self.cloud.device['type'] = 'devices.types.light.garland'
        await self.manager.sync(integration_id)
        device = self.manager.devices()[0]
        with self.manager.db:
            self.manager.db.execute('UPDATE devices SET kind_override=? WHERE id=?', ('cz', device['id']))
        await self.manager.sync(integration_id)
        device = self.manager.device(device['id'])
        self.assertEqual(device['kind'], 'cz')
        self.assertEqual(device['icon'], 'garland')
        self.assertEqual(device['kind_override'], 'cz')


class YandexApiTests(unittest.TestCase):
    def test_admin_csrf_and_configuration_failure(self):
        with TemporaryDirectory() as directory:
            app = create_app(ServerSettings(data_dir=directory, auth_db_path=str(Path(directory) / 'auth.sqlite3'), api_token='server-token', admin_username='admin', admin_password='admin-password'))
            shutil.copytree(PLUGIN_ROOT, Path(directory) / 'plugins/openhdo.yandex', ignore=shutil.ignore_patterns('node_modules', '__pycache__'))
            with TestClient(app) as client:
                client.post('/api/v1/plugins/openhdo.yandex/enable', headers={'Authorization': 'Bearer server-token'}).raise_for_status()
                path = '/api/v1/plugins/openhdo.yandex/api/login/start'
                self.assertEqual(client.post(path, json={}).status_code, 401)
                client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin-password'})
                self.assertEqual(client.post(path, json={}).status_code, 403)
                headers = {'X-OpenHDO-CSRF': client.cookies['openhdo_csrf']}
                self.assertEqual(client.post(path, json={}, headers=headers).status_code, 503)
                settings = '/api/v1/plugins/openhdo.yandex/api/settings'
                response = client.put(settings, json=CONFIG, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn('shared-secret', client.get(settings).text)
                client.post('/api/v1/auth/register', json={'username': 'user', 'password': 'user-password'})
                client.post('/api/v1/auth/login', json={'username': 'user', 'password': 'user-password'})
                headers = {'X-OpenHDO-CSRF': client.cookies['openhdo_csrf']}
                self.assertEqual(client.post(path, json={}, headers=headers).status_code, 403)

    def test_no_credentials_are_bundled_and_stored_secret_is_not_public(self):
        with TemporaryDirectory() as directory:
            manager = IntegrationManager(Path(directory) / 'devices.sqlite3')
            manifest = json.loads((PLUGIN_ROOT / 'hdo.json').read_text(encoding='utf-8'))
            context = PluginContext(manifest, Path(directory) / 'private', {'devices': manager, 'http': manager.client}, None)
            provider = plugin.YandexProvider(context)
            self.assertEqual(provider.settings(), {'client_id': '', 'configured': False})
            provider.save_settings(CONFIG)
            self.assertEqual(provider.settings(), {'client_id': 'public-id', 'configured': True})
            provider.save_settings({'client_id': 'public-id', 'client_secret': ''})
            self.assertEqual(context.store.get('oauth')['client_secret'], 'shared-secret')
            asyncio.run(context.close())
            asyncio.run(manager.close())
