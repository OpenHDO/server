"""Server-owned smart-home integrations and persistent device inventory."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Response
from pydantic import Field, JsonValue, SecretStr, StrictBool, StrictInt, field_validator

from .models import StrictModel, utc_now
from .tuya import REGIONS, TuyaCloud
from .tuya_account import TuyaAccount
from .service import ServiceError


class IntegrationInput(StrictModel):
    provider: Literal["tuya"] = "tuya"
    name: str = Field(min_length=1, max_length=128)
    region: Literal["auto", "eu", "us", "cn", "in", "eu_west", "us_east"] = "auto"
    access_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    secret: SecretStr = Field(min_length=1, max_length=256)
    uid: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class DeviceAction(StrictModel):
    code: str = Field(min_length=1, max_length=128)
    value: StrictBool | StrictInt | str | dict[str, StrictInt]


class TuyaLoginInput(StrictModel):
    name: str = Field(default="Tuya", min_length=1, max_length=128)
    user_code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    integration_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("name", "user_code", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class TuyaLoginView(StrictModel):
    id: str
    qr_image: str
    expires_in: int


class TuyaLoginResult(StrictModel):
    status: Literal["pending", "connected"]
    integration_id: str | None = None


class YandexLoginInput(StrictModel):
    name: str = Field(default="Yandex", min_length=1, max_length=128)
    integration_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class YandexLoginView(StrictModel):
    id: str
    user_code: str
    verification_url: Literal["https://oauth.yandex.ru/device", "https://ya.ru/device"]
    expires_in: int = Field(gt=0)
    interval: int = Field(ge=5)


class DeviceUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    area: str = Field(default="", max_length=128)
    enabled: StrictBool = True
    room_id: str | None = Field(default=None, min_length=1, max_length=128)
    kind_override: Literal['cz', 'dj'] | None = None


class RoomInput(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    device_ids: list[str] = Field(default_factory=list, max_length=10000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class RoomView(StrictModel):
    id: str
    name: str
    device_count: int = Field(ge=0)


class RoomsResponse(StrictModel):
    rooms: list[RoomView]


class IntegrationView(StrictModel):
    id: str
    provider: str
    name: str
    region: str
    access_id: str
    uid: str
    auth_method: Literal["cloud", "account", "yandex", "plugin"] = "cloud"
    status: Literal["connecting", "connected", "error"]
    error: str | None
    synced_at: str | None
    device_count: int = Field(ge=0)


class DeviceControl(StrictModel):
    code: str
    name: str
    type: Literal["Boolean", "Integer", "Enum", "Json"]
    constraints: dict[str, JsonValue]


class DeviceSnapshot(StrictModel):
    external_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    kind: str
    device_type: str | None = None
    available: bool
    state_stale: bool = False
    controls: list[DeviceControl]
    state: dict[str, JsonValue]
    status_specs: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    product_name: str
    updated_at: str | None
    state_revision: int = Field(default=0, ge=0)
    icon: Literal['garland'] | None = None


class DeviceView(DeviceSnapshot):
    id: str
    integration_id: str
    area: str
    enabled: bool
    room_id: str | None = None
    kind_override: Literal['cz', 'dj'] | None = None


class IntegrationsResponse(StrictModel):
    integrations: list[IntegrationView]


class DevicesResponse(StrictModel):
    devices: list[DeviceView]


class IntegrationManager:
    def __init__(self, path: Path, client=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS integrations (
                id TEXT PRIMARY KEY, provider TEXT, name TEXT, region TEXT, access_id TEXT, secret TEXT, uid TEXT,
                status TEXT, error TEXT, synced_at TEXT, UNIQUE(region,access_id,uid));
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY, integration_id TEXT, external_id TEXT, data TEXT,
                name TEXT, area TEXT DEFAULT '', enabled INTEGER DEFAULT 1);
        """)
        self.db.execute("CREATE TABLE IF NOT EXISTS light_commands(device_id TEXT, key TEXT, fingerprint TEXT, result TEXT, PRIMARY KEY(device_id,key))")
        self.db.commit()
        if "auth_method" not in {row["name"] for row in self.db.execute("PRAGMA table_info(integrations)")}:
            self.db.execute("ALTER TABLE integrations ADD COLUMN auth_method TEXT NOT NULL DEFAULT 'cloud'")
            self.db.commit()
        self.db.execute("CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_key TEXT NOT NULL UNIQUE)")
        if "room_id" not in {row["name"] for row in self.db.execute("PRAGMA table_info(devices)")}:
            self.db.execute("ALTER TABLE devices ADD COLUMN room_id TEXT")
        if "kind_override" not in {row["name"] for row in self.db.execute("PRAGMA table_info(devices)")}:
            self.db.execute("ALTER TABLE devices ADD COLUMN kind_override TEXT")
        self.db.execute("CREATE INDEX IF NOT EXISTS devices_room_idx ON devices(room_id)")
        with self.db:
            for row in self.db.execute("SELECT DISTINCT area FROM devices WHERE room_id IS NULL AND trim(area)<>''").fetchall():
                room = self.room_for_name(row["area"])
                self.db.execute("UPDATE devices SET room_id=?,area=? WHERE room_id IS NULL AND area=?", (room["id"], room["name"], row["area"]))
        self.client = client or httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False)
        self.lock = asyncio.Lock()
        self.device_locks = {}
        self.sync_locks = {}
        self.plugin_providers = {}
        self.plugin_events = None
        self.tuya = TuyaCloud(self.client)
        self.account = TuyaAccount(self.client)
        self.logins = {}

    def integrations(self):
        return [dict(row) for row in self.db.execute("SELECT id,provider,name,region,access_id,uid,auth_method,status,error,synced_at,(SELECT count(*) FROM devices WHERE integration_id=integrations.id) AS device_count FROM integrations ORDER BY name,id")]

    def devices(self):
        result = []
        for row in self.db.execute("SELECT devices.*, integrations.status FROM devices JOIN integrations ON integration_id=integrations.id ORDER BY devices.id"):
            data = json.loads(row["data"])
            data.update(id=row["id"], integration_id=row["integration_id"], name=row["name"] or data["name"], area=row["area"], enabled=bool(row["enabled"]), room_id=row["room_id"])
            data['kind_override'] = row['kind_override']
            data['kind'] = row['kind_override'] or data['kind']
            data["state_stale"] = data.get("state_stale", False) or row["status"] != "connected"
            data["available"] = data["available"] and row["status"] == "connected" and data["enabled"]
            result.append(data)
        return result

    def entry(self, integration_id):
        row = self.db.execute("SELECT * FROM integrations WHERE id=?", (integration_id,)).fetchone()
        if row is None:
            raise ServiceError(404, "integration_not_found", "Integration not found")
        return dict(row)

    def rooms(self):
        return [dict(row) for row in self.db.execute("SELECT id,name,(SELECT count(*) FROM devices WHERE room_id=rooms.id) AS device_count FROM rooms ORDER BY name COLLATE NOCASE,id")]

    def room(self, room_id):
        room = next((room for room in self.rooms() if room["id"] == room_id), None)
        if room is None:
            raise ServiceError(404, "room_not_found", "Room not found")
        return room

    def room_for_name(self, name):
        name = name.strip()
        row = self.db.execute("SELECT id,name FROM rooms WHERE name_key=?", (name.casefold(),)).fetchone()
        if row:
            return dict(row)
        room = dict(id="room-" + uuid4().hex, name=name)
        self.db.execute("INSERT INTO rooms(id,name,name_key) VALUES(?,?,?)", (room["id"], name, name.casefold()))
        return room

    async def save_room(self, change, room_id=None):
        async with self.lock:
            if room_id is not None:
                self.room(room_id)
            ids = set(change.device_ids)
            if len(ids) != len(change.device_ids):
                raise ServiceError(422, "duplicate_device", "Device selection contains duplicates")
            if not ids.issubset({device["id"] for device in self.devices()}):
                raise ServiceError(404, "device_not_found", "Device not found")
            room_id = room_id or "room-" + uuid4().hex
            try:
                with self.db:
                    self.db.execute("INSERT INTO rooms(id,name,name_key) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,name_key=excluded.name_key", (room_id, change.name, change.name.casefold()))
                    self.db.execute("UPDATE devices SET room_id=NULL,area='' WHERE room_id=?", (room_id,))
                    for device_id in ids:
                        self.db.execute("UPDATE devices SET room_id=?,area=? WHERE id=?", (room_id, change.name, device_id))
            except sqlite3.IntegrityError:
                raise ServiceError(409, "room_exists", "A room with this name already exists") from None
            return self.room(room_id)

    async def delete_room(self, room_id):
        async with self.lock:
            self.room(room_id)
            with self.db:
                self.db.execute("UPDATE devices SET room_id=NULL,area='' WHERE room_id=?", (room_id,))
                self.db.execute("DELETE FROM rooms WHERE id=?", (room_id,))

    async def fetch_devices(self, entry, persist=True):
        try:
            save = self.persist_account if persist else lambda entry: None
            if entry.get("auth_method") == "plugin":
                provider = self.plugin_providers.get(entry["provider"])
                if not provider:
                    raise ServiceError(503, "provider_disabled", "Enable the provider plugin")
                try:
                    inventory = await asyncio.wait_for(provider.devices(json.loads(entry["secret"])), timeout=30)
                except ServiceError:
                    raise
                except Exception:
                    raise ServiceError(502, "plugin_provider_failed", "Provider inventory failed; check plugin logs") from None
            elif entry.get("auth_method") == "yandex":
                raise ServiceError(503, "provider_disabled", "Install and enable the Yandex plugin, then sign in with your own OAuth application.")
            else:
                inventory = await self.account.devices(entry, save) if entry.get("auth_method") == "account" else await self.tuya.devices(entry)
            return [DeviceSnapshot.model_validate(item).model_dump() for item in inventory]
        except (KeyError, TypeError, ValueError):
            raise ServiceError(502, "invalid_inventory", "The remote system returned an invalid device inventory") from None

    def persist_account(self, entry):
        with self.db:
            self.db.execute("UPDATE integrations SET secret=? WHERE id=? AND auth_method IN ('account','yandex')", (entry["secret"], entry["id"]))

    async def start_login(self, change, owner):
        async with self.lock:
            self.logins = {key: value for key, value in self.logins.items() if value["expires"] > time.monotonic()}
            if change.integration_id:
                if self.entry(change.integration_id)["provider"] != "tuya":
                    raise ServiceError(422, "provider_mismatch", "Provider cannot be changed")
            if len(self.logins) >= 16:
                raise ServiceError(429, "too_many_logins", "Too many sign-in attempts. Try again later.")
            token, image = await self.account.start(change.user_code)
            login_id = uuid4().hex
            self.logins[login_id] = {"owner": owner, "change": change, "token": token, "expires": time.monotonic() + 300, "connected": None}
            return {"id": login_id, "qr_image": image, "expires_in": 300}

    def login(self, login_id, owner):
        login = self.logins.get(login_id)
        if not login or login["owner"] != owner:
            raise ServiceError(404, "login_not_found", "Sign-in attempt not found")
        if login["expires"] <= time.monotonic():
            self.logins.pop(login_id, None)
            raise ServiceError(410, "login_expired", "QR code expired. Start sign-in again.")
        return login

    async def check_login(self, login_id, owner):
        async with self.lock:
            login = self.login(login_id, owner)
            if login["connected"]:
                return {"status": "connected", "integration_id": login["connected"]}
            change = login["change"]
            credentials = await self.account.check(change.user_code, login["token"])
            if credentials is None:
                return {"status": "pending"}
            previous = self.entry(change.integration_id) if change.integration_id else None
            if previous and previous["uid"] != credentials["token_info"]["uid"]:
                raise ServiceError(409, "account_mismatch", "Sign in to the same Tuya account to reconnect this integration")
            entry = {"id": change.integration_id or "integration-" + uuid4().hex, "provider": "tuya", "name": change.name,
                "region": credentials["endpoint"], "access_id": "", "uid": credentials["token_info"]["uid"],
                "secret": json.dumps({**credentials, "user_code": change.user_code}), "auth_method": "account"}
            if self.db.execute("SELECT id FROM integrations WHERE provider='tuya' AND uid=? AND id<>?", (entry["uid"], entry["id"])).fetchone():
                raise ServiceError(409, "integration_exists", "This Tuya account is already connected")
            devices = await self.fetch_devices(entry, persist=False)
            with self.db:
                self.db.execute("INSERT INTO integrations(id,provider,name,region,access_id,secret,uid,status,auth_method) VALUES(?,?,?,?,?,?,?,'connecting','account') ON CONFLICT(id) DO UPDATE SET name=excluded.name,region=excluded.region,access_id=excluded.access_id,secret=excluded.secret,uid=excluded.uid,auth_method='account'",
                    tuple(entry[key] for key in ("id", "provider", "name", "region", "access_id", "secret", "uid")))
            await self.sync_entry(entry, devices)
            login["connected"] = entry["id"]
            login["token"] = ""
            return {"status": "connected", "integration_id": entry["id"]}

    async def resolve_entry(self, change, integration_id, preferred_region=None):
        entry = dict(id=integration_id, provider="tuya", name=change.name, region=change.region, access_id=change.access_id, secret=change.secret.get_secret_value(), uid=change.uid)
        regions = [change.region] if change.region != "auto" else list(dict.fromkeys([region for region in [preferred_region, *REGIONS] if region]))
        for region in regions:
            entry["region"] = region
            try:
                return entry, await self.fetch_devices(entry)
            except ServiceError as error:
                if change.region != "auto" or error.code == "invalid_inventory":
                    raise
        raise ServiceError(502, "tuya_connection_failed", "Unable to connect to the Tuya account. Check credentials, account linking and API permissions.")

    async def sync_entry(self, entry, devices=None, command_device=None, revisions=None):
        try:
            revisions = revisions if revisions is not None else {device['id']: device['state_revision'] for device in self.devices() if device['integration_id'] == entry['id']}
            devices = await self.fetch_devices(entry) if devices is None else devices
            identifiers = set()
            changed_ids = []
            with self.db:
                for device in devices:
                    device_id = "device-" + hashlib.sha256((entry["id"] + ":" + device["external_id"]).encode()).hexdigest()[:32]
                    identifiers.add(device_id)
                    previous = self.db.execute("SELECT data FROM devices WHERE id=?", (device_id,)).fetchone()
                    previous_data = json.loads(previous["data"]) if previous else {}
                    busy = self.device_locks.get(device_id)
                    if previous and ((busy and busy.locked() and device_id != command_device) or previous_data.get('state_revision', 0) != revisions.get(device_id, 0)):
                        device['state'] = previous_data['state']
                        device['available'] = previous_data['available']
                        device['state_stale'] = previous_data.get('state_stale', False)
                    changed = previous_data.get("state") != device["state"] or previous_data.get("available") != device["available"] or previous_data.get("state_stale", False) != device.get("state_stale", False)
                    if changed:
                        changed_ids.append(device_id)
                    device["state_revision"] = previous_data.get("state_revision", 0) + int(changed)
                    device["updated_at"] = utc_now().isoformat() if changed else previous_data.get("updated_at")
                    DeviceView.model_validate(dict(device, id=device_id, integration_id=entry["id"], area="", enabled=True))
                    self.db.execute("INSERT INTO devices(id,integration_id,external_id,data) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (device_id, entry["id"], device["external_id"], json.dumps(device)))
                for row in self.db.execute("SELECT id,data FROM devices WHERE integration_id=?", (entry["id"],)).fetchall():
                    if row["id"] not in identifiers:
                        busy = self.device_locks.get(row['id'])
                        if (busy and busy.locked()) or json.loads(row['data']).get('state_revision', 0) != revisions.get(row['id'], 0):
                            continue
                        self.db.execute("DELETE FROM devices WHERE id=?", (row["id"],))
                self.db.execute("UPDATE integrations SET status='connected',error=NULL,synced_at=? WHERE id=?", (utc_now().isoformat(), entry["id"]))
        except (KeyError, TypeError, ValueError):
            error = ServiceError(502, "invalid_inventory", "The remote system returned an invalid device inventory")
            self.fail(entry, error.detail)
            raise error from None
        except ServiceError as error:
            self.fail(entry, error.detail)
            raise

        if self.plugin_events:
            await self.plugin_events("devices.updated", {"integration_id": entry["id"]})
            for device_id in changed_ids:
                await self.plugin_events("device.changed", self.device(device_id))

    def fail(self, entry, detail):
        with self.db:
            self.db.execute("UPDATE integrations SET status='error',error=? WHERE id=?", (detail, entry["id"]))

    async def add_plugin(self, provider, name, config, integration_id=None):
        if integration_id is not None and not isinstance(integration_id, str):
            raise ServiceError(422, "invalid_value", "Integration id must be a string")
        if provider not in self.plugin_providers:
            raise ServiceError(503, "provider_disabled", "Enable the provider plugin")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 128 or not isinstance(config, dict):
            raise ServiceError(422, "invalid_value", "A name and configuration object are required")
        async with self.lock:
            existing = self.entry(integration_id) if integration_id else None
            if existing and (existing["provider"] != provider or existing["auth_method"] != "plugin"):
                raise ServiceError(422, "provider_mismatch", "Provider cannot be changed")
            id = integration_id or "integration-" + uuid4().hex
            entry = dict(id=id, provider=provider, name=name.strip(), region="", access_id=provider,
                         secret=json.dumps(config), uid=id, auth_method="plugin")
            devices = await self.fetch_devices(entry)
            with self.db:
                self.db.execute("INSERT INTO integrations(id,provider,name,region,access_id,secret,uid,auth_method,status) VALUES(?,?,?,?,?,?,?,?,'connecting') ON CONFLICT(id) DO UPDATE SET name=excluded.name,secret=excluded.secret",
                                tuple(entry[k] for k in ("id","provider","name","region","access_id","secret","uid","auth_method")))
            try:
                await self.sync_entry(entry, devices)
            except Exception:
                with self.db:
                    if existing:
                        self.db.execute("UPDATE integrations SET name=?,secret=? WHERE id=?", (existing["name"], existing["secret"], id))
                    else:
                        self.db.execute("DELETE FROM devices WHERE integration_id=?", (id,))
                        self.db.execute("DELETE FROM integrations WHERE id=?", (id,))
                raise
            return next(item for item in self.integrations() if item["id"] == id)

    async def add(self, change):
        async with self.lock:
            entry, devices = await self.resolve_entry(change, "integration-" + uuid4().hex)
            if self.db.execute("SELECT id FROM integrations WHERE region=? AND access_id=? AND uid=?", (entry["region"], entry["access_id"], entry["uid"])).fetchone():
                raise ServiceError(409, "integration_exists", "This Tuya account is already connected")
            with self.db:
                self.db.execute("INSERT INTO integrations(id,provider,name,region,access_id,secret,uid,status) VALUES(?,?,?,?,?,?,?,'connecting')", tuple(entry[key] for key in ("id", "provider", "name", "region", "access_id", "secret", "uid")))
            try:
                await self.sync_entry(entry, devices)
            except ServiceError:
                with self.db:
                    self.db.execute("DELETE FROM integrations WHERE id=?", (entry["id"],))
                raise
            return next(item for item in self.integrations() if item["id"] == entry["id"])

    async def sync(self, integration_id):
        async with self.sync_locks.setdefault(integration_id, asyncio.Lock()):
            entry = self.entry(integration_id)
            revisions = {device['id']: device['state_revision'] for device in self.devices() if device['integration_id'] == integration_id}
            try:
                inventory = await self.fetch_devices(entry)
            except ServiceError as error:
                self.fail(entry, error.detail)
                raise
            async with self.lock:
                self.entry(integration_id)
                await self.sync_entry(entry, inventory, revisions=revisions)
            return next(item for item in self.integrations() if item["id"] == integration_id)

    async def delete(self, integration_id):
        async with self.lock:
            self.entry(integration_id)
            with self.db:
                self.db.execute("DELETE FROM light_commands WHERE device_id IN (SELECT id FROM devices WHERE integration_id=?)", (integration_id,))
                self.db.execute("DELETE FROM devices WHERE integration_id=?", (integration_id,))
                self.db.execute("DELETE FROM integrations WHERE id=?", (integration_id,))

    def device(self, device_id):
        device = next((item for item in self.devices() if item["id"] == device_id), None)
        if device is None:
            raise ServiceError(404, "device_not_found", "Device not found")
        return device

    async def action(self, device_id, change):
        async with self.device_locks.setdefault(device_id, asyncio.Lock()):
            device = self.device(device_id)
            if not device["available"]:
                raise ServiceError(409, "device_unavailable", "Device is unavailable or disabled")
            control = next((item for item in device["controls"] if item["code"] == change.code), None)
            if control is None:
                raise ServiceError(422, "unsupported_action", "This device does not support the command")
            rules = control["constraints"]
            value = change.value
            valid = False
            if control["type"] == "Boolean":
                valid = type(value) is bool
            elif control["type"] == "Integer":
                valid = type(value) is int and rules["min"] <= value <= rules["max"] and (
                    (value - rules.get('step_origin', rules['min'])) % rules.get("step", 1) == 0 or
                    ('step_origin' in rules and value in {rules['min'], rules['max']}))
            elif control["type"] == "Enum":
                valid = isinstance(value, str) and value in rules["range"]
            elif control["type"] == "Json":
                valid = isinstance(value, dict) and set(value) == {"h", "s", "v"} and all(rules[channel]["min"] <= value[channel] <= rules[channel]["max"] and (value[channel] - rules[channel]["min"]) % rules[channel].get("step", 1) == 0 for channel in value)
            if not valid:
                raise ServiceError(422, "invalid_value", "Value does not match the device function specification")
            entry = self.entry(device["integration_id"])
            preceding = []
            mode = next((item for item in device["controls"] if item["code"] == "work_mode" and item["type"] == "Enum"), None)
            desired_mode = "colour" if change.code in {"colour_data", "colour_data_v2"} else "white" if change.code in {"bright_value", "bright_value_v2", "temp_value", "temp_value_v2"} else None
            if desired_mode and mode and desired_mode in mode["constraints"]["range"]:
                preceding.append({"code": "work_mode", "value": desired_mode})
            color = next((item for item in device['controls'] if item['code'] in {'colour_data', 'colour_data_v2'} and item['type'] == 'Json'), None)
            brightness = next((item for item in device['controls'] if item['code'] in {'bright_value', 'bright_value_v2'}), None)
            hsv = device['state'].get(color['code']) if color else None
            selecting_white = change.code in {'temp_value', 'temp_value_v2'} or (change.code == 'work_mode' and value == 'white')
            if selecting_white and device['state'].get('work_mode') == 'colour' and isinstance(hsv, dict) and brightness:
                # White and RGB channels have independent brightness; keep the visible level on mode change.
                bright_rules = brightness['constraints']
                requested = hsv['v'] / max(1, color['constraints']['v']['max']) * bright_rules['max']
                origin = bright_rules.get('step_origin', bright_rules['min'])
                step = bright_rules.get('step', 1)
                maximum = bright_rules['max'] if 'step_origin' in bright_rules else origin + (bright_rules['max'] - origin) // step * step
                preserved = max(bright_rules['min'], min(maximum, origin + round((requested - origin) / step) * step))
                preceding.append({'code': brightness['code'], 'value': preserved})
            acknowledged = False
            updates = None
            try:
                if entry.get("auth_method") == "plugin":
                    provider = self.plugin_providers.get(entry["provider"])
                    if provider is None:
                        raise ServiceError(503, "provider_disabled", "Enable the provider plugin")
                    try:
                        config = json.loads(entry["secret"])
                        if hasattr(provider, 'command_batch'):
                            updates = await asyncio.wait_for(provider.command_batch(config, device["external_id"], change.code, value, preceding), timeout=30)
                        else:
                            for command in preceding:
                                await asyncio.wait_for(provider.command(config, device["external_id"], command['code'], command['value']), timeout=30)
                            updates = await asyncio.wait_for(provider.command(config, device["external_id"], change.code, value), timeout=30)
                        acknowledged = getattr(provider, 'acknowledges_commands', False)
                    except ServiceError:
                        raise
                    except Exception:
                        raise ServiceError(502, "plugin_provider_failed", "Provider command failed; check plugin logs") from None
                elif entry.get("auth_method") == "account":
                    await self.account.command(entry, self.persist_account, device["external_id"], change.code, value, preceding)
                else:
                    await self.tuya.command(entry, device["external_id"], change.code, value, preceding)
            except ServiceError as error:
                if error.code.endswith('_device_unavailable'):
                    with self.db:
                        row = self.db.execute('SELECT data FROM devices WHERE id=?', (device_id,)).fetchone()
                        if row:
                            data = json.loads(row['data'])
                            data['available'] = False
                            data['state_revision'] += 1
                            data['updated_at'] = utc_now().isoformat()
                            self.db.execute('UPDATE devices SET data=? WHERE id=?', (json.dumps(data), device_id))
                elif not error.code.endswith('_command_rejected'):
                    self.fail(entry, error.detail)
                raise
            if acknowledged:
                # DONE acknowledges this value; reconcile with the cloud during automatic sync.
                with self.db:
                    row = self.db.execute('SELECT data FROM devices WHERE id=?', (device_id,)).fetchone()
                    if row is None:
                        raise ServiceError(404, 'device_not_found', 'Device not found')
                    data = json.loads(row['data'])
                    data['state_stale'] = False
                    if rules.get('retrievable', True) and not rules.get('relative'):
                        data['state'][change.code] = value
                    else:
                        data['state'].pop(change.code, None)
                    data['state'].update(updates or {})
                    for command in preceding:
                        data['state'][command['code']] = command['value']
                    if desired_mode and change.code not in {'bright_value', 'bright_value_v2'}:
                        data['state']['work_mode'] = desired_mode
                    elif change.code == 'color_scene':
                        data['state']['work_mode'] = 'scene'
                    data['state_revision'] += 1
                    data['updated_at'] = utc_now().isoformat()
                    self.db.execute('UPDATE devices SET data=? WHERE id=?', (json.dumps(data), device_id))
                result = self.device(device_id)
                if self.plugin_events:
                    await self.plugin_events('device.changed', result)
                return result
            try:
                await self.sync_entry(entry, command_device=device_id)
            except ServiceError:
                # The command was accepted; failed readback must not invite a duplicate command.
                pass
            return self.device(device_id)

    async def poll(self, integration_id):
        entry = self.entry(integration_id)
        interval = getattr(self.plugin_providers.get(entry['provider']), 'poll_interval', 5)
        delay = interval
        while True:
            try:
                await self.sync(integration_id)
                delay = interval
            except ServiceError as error:
                if error.code == 'integration_not_found':
                    return
                delay = min(delay * 2, 60)
            await asyncio.sleep(delay)

    async def run(self):
        workers = {}
        try:
            while True:
                identifiers = {entry['id'] for entry in self.integrations()}
                for integration_id in identifiers:
                    if integration_id not in workers:
                        workers[integration_id] = asyncio.create_task(self.poll(integration_id))
                for integration_id in list(workers):
                    if integration_id not in identifiers:
                        task = workers.pop(integration_id)
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                await asyncio.sleep(1)
        finally:
            for task in workers.values():
                task.cancel()
            await asyncio.gather(*workers.values(), return_exceptions=True)

    async def close(self):
        self.logins.clear()
        await self.client.aclose()
        self.db.close()


def integration_router(manager, require_authorization, require_admin, require_user, require_csrf):
    router = APIRouter(prefix="/api/v1")
    read = [Depends(require_authorization)]
    admin = [Depends(require_admin), Depends(require_csrf)]

    def login_owner(principal):
        return principal.user.id if principal.user else principal.kind

    @router.post("/integrations/tuya/login", response_model=TuyaLoginView, status_code=201, dependencies=admin)
    async def start_tuya_login(change: TuyaLoginInput, principal=Depends(require_admin)):
        return await manager.start_login(change, login_owner(principal))

    @router.post("/integrations/tuya/login/{login_id}", response_model=TuyaLoginResult, dependencies=admin)
    async def check_tuya_login(login_id: str, principal=Depends(require_admin)):
        return await manager.check_login(login_id, login_owner(principal))

    @router.delete("/integrations/tuya/login/{login_id}", status_code=204, dependencies=admin)
    async def cancel_tuya_login(login_id: str, principal=Depends(require_admin)):
        async with manager.lock:
            manager.login(login_id, login_owner(principal))
            manager.logins.pop(login_id, None)
        return Response(status_code=204)

    @router.get("/integrations", response_model=IntegrationsResponse, dependencies=read)
    async def list_integrations():
        return {"integrations": manager.integrations()}

    @router.post("/integrations", response_model=IntegrationView, status_code=201, dependencies=admin)
    async def add_integration(change: IntegrationInput):
        return await manager.add(change)

    @router.put("/integrations/{integration_id}", response_model=IntegrationView, dependencies=admin)
    async def update_integration(integration_id: str, change: IntegrationInput):
        async with manager.lock:
            previous = manager.entry(integration_id)
            if previous["auth_method"] in {"account", "yandex"}:
                raise ServiceError(409, "account_authentication_required", "Reconnect this integration through account sign-in")
            if change.provider != previous["provider"]:
                raise ServiceError(422, "provider_mismatch", "Provider cannot be changed")
            entry, devices = await manager.resolve_entry(change, integration_id, previous["region"])
            try:
                with manager.db:
                    manager.db.execute("UPDATE integrations SET name=?,region=?,access_id=?,secret=?,uid=? WHERE id=?", (entry["name"], entry["region"], entry["access_id"], entry["secret"], entry["uid"], integration_id))
            except sqlite3.IntegrityError:
                raise ServiceError(409, "integration_exists", "This Tuya account is already connected") from None
            await manager.sync_entry(entry, devices)
            return next(item for item in manager.integrations() if item["id"] == integration_id)

    @router.post("/integrations/{integration_id}/sync", response_model=IntegrationView, dependencies=admin)
    async def sync_integration(integration_id: str):
        manager.tuya.functions.clear()
        return await manager.sync(integration_id)

    @router.delete("/integrations/{integration_id}", status_code=204, dependencies=admin)
    async def delete_integration(integration_id: str):
        await manager.delete(integration_id)
        return Response(status_code=204)

    @router.get("/devices", response_model=DevicesResponse, dependencies=read)
    async def list_devices():
        return {"devices": manager.devices()}

    @router.get("/rooms", response_model=RoomsResponse, dependencies=read)
    async def list_rooms():
        return {"rooms": manager.rooms()}

    @router.post("/rooms", response_model=RoomView, status_code=201, dependencies=admin)
    async def add_room(change: RoomInput):
        return await manager.save_room(change)

    @router.put("/rooms/{room_id}", response_model=RoomView, dependencies=admin)
    async def update_room(room_id: str, change: RoomInput):
        return await manager.save_room(change, room_id)

    @router.delete("/rooms/{room_id}", status_code=204, dependencies=admin)
    async def remove_room(room_id: str):
        await manager.delete_room(room_id)
        return Response(status_code=204)

    @router.get("/devices/{device_id}", response_model=DeviceView, dependencies=read)
    async def get_device(device_id: str):
        return manager.device(device_id)

    @router.patch("/devices/{device_id}", response_model=DeviceView, dependencies=admin)
    async def update_device(device_id: str, change: DeviceUpdate):
        async with manager.lock:
            previous = manager.device(device_id)
            with manager.db:
                if "room_id" in change.model_fields_set:
                    room = manager.room(change.room_id) if change.room_id is not None else None
                elif "area" in change.model_fields_set:
                    room = manager.room_for_name(change.area) if change.area.strip() else None
                else:
                    room = manager.room(previous["room_id"]) if previous["room_id"] else None
                manager.db.execute("UPDATE devices SET name=?,area=?,enabled=?,room_id=? WHERE id=?", (change.name.strip() or None, room["name"] if room else "", change.enabled, room["id"] if room else None, device_id))
                if 'kind_override' in change.model_fields_set:
                    manager.db.execute('UPDATE devices SET kind_override=? WHERE id=?', (change.kind_override, device_id))
            return manager.device(device_id)

    @router.post("/devices/{device_id}/actions", response_model=DeviceView, dependencies=[Depends(require_user), Depends(require_csrf)])
    async def device_action(device_id: str, change: DeviceAction):
        return await manager.action(device_id, change)

    return router
