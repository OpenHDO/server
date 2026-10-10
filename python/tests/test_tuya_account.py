import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

import httpx
import requests
from fastapi.testclient import TestClient

from openhdo_server.app import create_app
from openhdo_server.config import ServerSettings
from openhdo_server.integrations import IntegrationManager, TuyaLoginInput, DeviceAction, RoomInput
from openhdo_server.service import ServiceError
from openhdo_server.tuya_account import account_credentials


def authorization():
    return dict(endpoint="https://apigw.tuyaeu.com", uid="user-id", terminal_id="terminal",
                access_token="private-access", refresh_token="private-refresh", expire_time=7200, t=int(time.time() * 1000))


class SharingCloud:
    def __init__(self):
        self.confirmed = False
        self.failed = False
        self.power = False
        self.refresh = False
        self.accepted = True
        self.commands = []

    def login(self, request):
        if request.method == "POST":
            result = {"qrcode": "qr-token"}
        elif not self.confirmed:
            return httpx.Response(200, json={"success": False, "code": "not_scanned", "msg": "private-refresh"})
        else:
            result = authorization()
        return httpx.Response(200, json={"success": True, "result": result, "t": int(time.time() * 1000)})

    def api(self, token, client_id, user_code, endpoint, listener):
        cloud = self
        class Api:
            token_info = token
            session = requests.Session()
            def refresh_access_token_if_need(self):
                if cloud.refresh:
                    self.token_info.access_token = "renewed-access"
                    self.token_info.refresh_token = "renewed-refresh"
                    self.token_info.expire_time = int(time.time() * 1000) + 7200000
            def get(self, path, params=None):
                if cloud.failed:
                    raise RuntimeError("private-access private-refresh")
                if path == "/v1.0/m/life/users/homes":
                    result = [{"ownerId": 1, "name": "Home"}]
                elif path == "/v1.0/m/life/ha/home/devices":
                    assert params == {"homeId": "1"}
                    result = [{"id": "socket-1", "category": "cz", "name": "Socket", "online": True,
                               "status": [{"code": "switch", "value": cloud.power}, {"code": "cur_power", "value": 125}]}]
                elif path.endswith("/specifications"):
                    result = {"functions": [{"code": "switch", "type": "Boolean", "values": "{}"}],
                              "status": [{"code": "cur_power", "values": '{"unit":"W","scale":1}'}]}
                else:
                    raise AssertionError(path)
                return {"success": True, "result": result}
            def post(self, path, params, body):
                cloud.commands.append(body)
                if cloud.accepted:
                    cloud.power = body["commands"][-1]["value"]
                return {"success": True, "result": cloud.accepted}
        return Api()


class AccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_reads_and_commands_share_refreshed_credentials(self):
        observed = []
        async def execute(entry, persist, operation):
            observed.append(entry['secret'])
            await asyncio.sleep(0)
            entry['secret'] = 'renewed'
        with patch.object(self.manager.account, 'execute_locked', execute):
            await asyncio.gather(*(self.manager.account.execute({'id':'account','secret':'expired'}, lambda entry: None, None) for _ in range(3)))
        self.assertEqual(observed, ['expired', 'renewed', 'renewed'])

    async def test_external_state_changes_are_not_cached_with_specifications(self):
        integration_id, _ = await self.connect()
        initial = self.manager.devices()[0]
        specifications = dict(self.manager.account.specifications)
        self.cloud.power = True
        await self.manager.sync(integration_id)
        current = self.manager.devices()[0]
        self.assertTrue(current['state']['switch'])
        self.assertGreater(current['state_revision'], initial['state_revision'])
        self.assertEqual(self.manager.account.specifications, specifications)
        self.assertEqual(self.cloud.commands, [])
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "integrations.sqlite3"
        self.cloud = SharingCloud()
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.cloud.login)))
        self.sdk = patch("openhdo_server.tuya_account.CustomerApi", side_effect=self.cloud.api)
        self.sdk.start()

    async def asyncTearDown(self):
        await self.manager.close()
        self.sdk.stop()
        self.directory.cleanup()

    async def connect(self, integration_id=None):
        login = await self.manager.start_login(TuyaLoginInput(user_code="code", integration_id=integration_id), "owner")
        self.cloud.confirmed = True
        result = await self.manager.check_login(login["id"], "owner")
        return result["integration_id"], login["id"]

    async def test_qr_waits_for_confirmation_then_imports_and_controls(self):
        login = await self.manager.start_login(TuyaLoginInput(user_code="code"), "owner")
        self.assertTrue(login["qr_image"].startswith("data:image/svg+xml;base64,"))
        self.assertEqual(await self.manager.check_login(login["id"], "owner"), {"status": "pending"})
        self.assertEqual(self.manager.integrations(), [])
        self.cloud.confirmed = True
        result = await self.manager.check_login(login["id"], "owner")
        self.assertEqual(await self.manager.check_login(login["id"], "owner"), result)
        self.assertEqual(len(self.manager.integrations()), 1)
        self.assertNotIn("private", json.dumps(self.manager.integrations()))
        device = self.manager.devices()[0]
        self.assertEqual(device["status_specs"]["cur_power"], {"unit": "W", "scale": 1})
        await self.manager.action(device["id"], DeviceAction(code="switch", value=True))
        self.assertTrue(self.manager.device(device["id"])["state"]["switch"])
        self.cloud.accepted = False
        with self.assertRaises(ServiceError):
            await self.manager.action(device["id"], DeviceAction(code="switch", value=False))

    async def test_refresh_persists_and_restart_preserves_room_name_and_ids(self):
        integration_id, _ = await self.connect()
        device = self.manager.devices()[0]
        room = await self.manager.save_room(RoomInput(name="Study", device_ids=[device["id"]]))
        self.manager.db.execute("UPDATE devices SET name='Desk socket' WHERE id=?", (device["id"],))
        self.manager.db.commit()
        self.cloud.refresh = True
        await self.manager.sync(integration_id)
        self.assertIn("renewed-refresh", self.manager.entry(integration_id)["secret"])
        await self.manager.close()
        self.manager = IntegrationManager(self.path, httpx.AsyncClient(transport=httpx.MockTransport(self.cloud.login)))
        await self.manager.sync(integration_id)
        restored = self.manager.devices()[0]
        self.assertEqual((restored["id"], restored["name"], restored["room_id"]), (device["id"], "Desk socket", room["id"]))
        # Simulate the persisted shape of an older developer-key connection.
        with self.manager.db:
            self.manager.db.execute("UPDATE integrations SET auth_method='cloud',region='eu',access_id='legacy',secret='legacy-secret' WHERE id=?", (integration_id,))
        await self.connect(integration_id)
        self.assertEqual(self.manager.entry(integration_id)["auth_method"], "account")
        self.assertEqual(self.manager.devices()[0]["id"], device["id"])
        self.assertEqual(self.manager.devices()[0]["room_id"], room["id"])

    async def test_duplicate_account_failed_reconnect_and_read_preserve_inventory(self):
        integration_id, _ = await self.connect()
        with self.assertRaises(ServiceError) as duplicate:
            await self.connect()
        self.assertEqual(duplicate.exception.status_code, 409)
        previous = self.manager.entry(integration_id)
        self.cloud.failed = True
        with self.assertRaises(ServiceError) as failed:
            await self.connect(integration_id)
        self.assertNotIn("private", failed.exception.detail)
        self.assertEqual(self.manager.entry(integration_id)["secret"], previous["secret"])
        with self.assertRaises(ServiceError):
            await self.manager.sync(integration_id)
        self.assertEqual(len(self.manager.devices()), 1)
        self.assertFalse(self.manager.devices()[0]["available"])

    async def test_login_is_owner_bound_and_expires(self):
        login = await self.manager.start_login(TuyaLoginInput(user_code="code"), "owner")
        with self.assertRaises(ServiceError) as wrong_owner:
            await self.manager.check_login(login["id"], "another")
        self.assertEqual(wrong_owner.exception.status_code, 404)
        self.manager.logins[login["id"]]["expires"] = 0
        with self.assertRaises(ServiceError) as expired:
            await self.manager.check_login(login["id"], "owner")
        self.assertEqual(expired.exception.status_code, 410)

    def test_login_rejects_foreign_endpoints_and_invalid_credentials(self):
        for endpoint in ("http://apigw.tuyaeu.com", "https://evil.test", "https://tuyaeu.com.evil.test", "https://user@apigw.tuyaeu.com", "https://apigw.tuyaeu.com:8000", "https://apigw.tuyaeu.com/private"):
            with self.assertRaises(ServiceError):
                account_credentials({**authorization(), "endpoint": endpoint})
        for invalid in ({"expire_time": 0}, {"access_token": ""}, {"t": None}):
            with self.assertRaises(ServiceError):
                account_credentials({**authorization(), **invalid})

    async def test_real_sdk_refresh_and_encrypted_command_transport(self):
        from tuya_sharing import customerapi as sdk
        from openhdo_server.tuya_account import TuyaAccount
        entry = {"id": "test", "secret": json.dumps({**account_credentials(authorization()), "user_code": "code"})}
        credentials = json.loads(entry["secret"])
        credentials["token_info"]["t"] = 1
        entry["secret"] = json.dumps(credentials)
        refresh = "private-refresh"
        calls = []
        saved = []
        def transport(session, method, url, **kwargs):
            nonlocal refresh
            self.assertEqual(kwargs["timeout"], 10)
            self.assertFalse(kwargs["allow_redirects"])
            rid = kwargs["headers"]["X-requestId"]
            secret = sdk._secret_generating(rid, "", hashlib.md5((rid + refresh).encode()).hexdigest())
            if "/token/" in url:
                result = {"uid": "user-id", "accessToken": "renewed-access", "refreshToken": "renewed-refresh", "expireTime": 7200}
                encrypted = sdk._aes_gcm_encrypt(json.dumps(result), secret).decode()
                refresh = "renewed-refresh"
            else:
                self.assertEqual(kwargs["headers"]["X-token"], "renewed-access")
                calls.append(json.loads(sdk._aex_gcm_decrypt(kwargs["json"]["encdata"], secret)))
                encrypted = sdk._aes_gcm_encrypt("true", secret).decode()
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps({"success": True, "result": encrypted, "t": int(time.time() * 1000)}).encode()
            return response
        # Restore the real SDK to exercise its encryption and automatic refresh.
        self.sdk.stop()
        with patch("requests.Session.request", transport):
            await TuyaAccount(self.manager.client).command(entry, lambda value: saved.append(json.loads(value["secret"])), "socket-1", "switch", True)
        self.sdk.start()
        self.assertEqual(calls, [{"commands": [{"code": "switch", "value": True}]}])
        self.assertEqual(saved[0]["token_info"]["refresh_token"], "renewed-refresh")


class AccountApiTests(unittest.TestCase):
    def test_admin_csrf_ownership_cancellation_and_credentials_privacy(self):
        with TemporaryDirectory() as directory:
            app = create_app(ServerSettings(data_dir=directory, auth_db_path=str(Path(directory) / "auth.sqlite3"),
                api_token="server-token", admin_username="admin", admin_password="admin-password"))
            manager = app.state.integrations
            asyncio.run(manager.client.aclose())
            cloud = SharingCloud()
            manager.client = httpx.AsyncClient(transport=httpx.MockTransport(cloud.login))
            manager.account.client = manager.client
            with patch("openhdo_server.tuya_account.CustomerApi", side_effect=cloud.api), TestClient(app) as client:
                path = "/api/v1/integrations/tuya/login"
                values = {"user_code": "code"}
                self.assertEqual(client.post(path, json=values).status_code, 401)
                client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-password"})
                self.assertEqual(client.post(path, json=values).status_code, 403)
                headers = {"X-OpenHDO-CSRF": client.cookies["openhdo_csrf"]}
                login = client.post(path, json=values, headers=headers)
                self.assertEqual(login.status_code, 201, login.text)
                check = path + "/" + login.json()["id"]
                self.assertEqual(client.post(check, headers={"Authorization": "Bearer server-token"}).status_code, 404)
                self.assertEqual(client.post(check, headers=headers).json()["status"], "pending")
                cloud.confirmed = True
                response = client.post(check, headers=headers)
                self.assertEqual(response.json()["status"], "connected", response.text)
                self.assertNotIn("private", response.text)
                self.assertNotIn("private", client.get("/api/v1/integrations").text)
                self.assertEqual(client.delete(check, headers=headers).status_code, 204)
                self.assertEqual(client.post(check, headers=headers).status_code, 404)
                client.post("/api/v1/auth/register", json={"username": "user", "password": "user-password"})
                client.post("/api/v1/auth/login", json={"username": "user", "password": "user-password"})
                user_headers = {"X-OpenHDO-CSRF": client.cookies["openhdo_csrf"]}
                self.assertEqual(client.post(path, json=values, headers=user_headers).status_code, 403)
