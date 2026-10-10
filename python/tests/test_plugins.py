import asyncio
import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openhdo_plugin import PluginError, pack, unpack
from openhdo_server.plugins import PluginManager


def source(tmp, id="example", code=None, **changes):
    directory = tmp / id
    directory.mkdir(parents=True)
    manifest = {"schemaVersion": 1, "apiVersion": 1, "id": id, "name": id, "version": "1.0.0", **changes}
    if code:
        manifest["entrypoints"] = {"python": "backend/plugin.py"}
        (directory / "backend").mkdir()
        (directory / "backend/plugin.py").write_text(code, "utf-8")
    (directory / "hdo.json").write_text(json.dumps(manifest), "utf-8")
    return directory


def test_pack_deterministic_and_roundtrip(tmp_path):
    folder = source(tmp_path)
    (folder / "web").mkdir(); (folder / "web/icon.svg").write_text("<svg/>")
    a, b = tmp_path / "a.hdop", tmp_path / "b.hdop"
    pack(folder, a); pack(folder, b)
    assert a.read_bytes() == b.read_bytes()
    assert unpack(a, tmp_path / "out")["id"] == "example"


@pytest.mark.parametrize("path", ["../outside", "/absolute", "a/../../outside", "C:/escape", "a\\escape", "a/./file"])
def test_reject_traversal_before_writing(tmp_path, path):
    archive = tmp_path / "bad.hdop"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(path, "bad")
    with pytest.raises(PluginError): unpack(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_reject_tamper_and_case_collisions(tmp_path):
    package = pack(source(tmp_path), tmp_path / "plugin.hdop")
    with zipfile.ZipFile(package, "a") as z: z.writestr("extra.py", "evil")
    with pytest.raises(PluginError): unpack(package, tmp_path / "out")
    with zipfile.ZipFile(tmp_path / "case.hdop", "w") as z:
        z.writestr("Foo.js", "1"); z.writestr("foo.js", "2")
    with pytest.raises(PluginError): unpack(tmp_path / "case.hdop", tmp_path / "out")


def test_reject_symlink(tmp_path):
    archive = tmp_path / "bad.hdop"
    info = zipfile.ZipInfo("link"); info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as z: z.writestr(info, "../outside")
    with pytest.raises(PluginError): unpack(archive, tmp_path / "out")


def test_lifecycle_update_rollback_and_data_retained(tmp_path):
    async def run():
        manager = PluginManager(tmp_path / "data")
        folder = source(tmp_path / "sources", code="def activate(ctx):\n    ctx.store.set('count', ctx.store.get('count', 0) + 1)\n", permissions=["storage"])
        package = pack(folder, tmp_path / "plugin.hdop")
        await manager.install(package)
        assert not manager.contexts  # install never executes code
        await manager.enable("example", True)
        assert manager.contexts["example"].store.get("count") == 1
        manifest = json.loads((folder / "hdo.json").read_text()); manifest["version"] = "1.1.0"
        (folder / "hdo.json").write_text(json.dumps(manifest))
        (folder / "backend/plugin.py").write_text("def activate(ctx):\n    raise RuntimeError('broken upgrade')\n")
        pack(folder, package)
        with pytest.raises(RuntimeError): await manager.install(package)
        assert manager.records["example"]["manifest"]["version"] == "1.0.0"
        assert manager.contexts["example"].store.get("count") == 2
        await manager.remove("example")
        assert (tmp_path / "data/plugin-data/example/state.sqlite3").is_file()
        assert not (tmp_path / "data/plugins/example").exists()
        await manager.close()
    asyncio.run(run())


def test_dependencies_disable_and_restart(tmp_path):
    async def run():
        manager = PluginManager(tmp_path / "data")
        for id, dependencies in [("base", {}), ("consumer", {"base": 1})]:
            folder = source(tmp_path / "src", id, dependencies=dependencies)
            await manager.install(pack(folder, tmp_path / f"{id}.hdop"))
        with pytest.raises(PluginError): await manager.enable("consumer", True)
        await manager.enable("base", True); await manager.enable("consumer", True)
        with pytest.raises(PluginError): await manager.enable("base", False)
        await manager.close()
        restored = PluginManager(tmp_path / "data"); await restored.start()
        assert set(restored.contexts) == {"base", "consumer"}
        await restored.close()
    asyncio.run(run())


def test_capabilities_and_assets(tmp_path):
    async def run():
        manager = PluginManager(tmp_path / "data")
        folder = source(tmp_path / "src", code="def activate(ctx):\n    ctx.store.set('secret', 'x')\n")
        await manager.install(pack(folder, tmp_path / "bad.hdop"))
        with pytest.raises(PermissionError): await manager.enable("example", True)
        assert "example" not in manager.contexts
        with pytest.raises(PluginError): manager.asset("example", "backend/plugin.py")
        await manager.close()
    asyncio.run(run())


def test_events_do_not_hold_device_locks(tmp_path):
    async def run():
        manager = PluginManager(tmp_path / "data"); await manager.start()
        folder = source(tmp_path / "src", code="def activate(ctx):\n    ctx.on('device.changed', lambda event: ctx.store.set('event', event['payload']))\n", permissions=["storage", "events"])
        await manager.install(pack(folder, tmp_path / "event.hdop")); await manager.enable("example", True)
        await manager.emit("device.changed", {"id": "one"})
        await asyncio.sleep(.02)
        assert manager.contexts["example"].store.get("event") == {"id": "one"}
        await manager.close()
    asyncio.run(run())


def test_provider_uses_existing_inventory_and_controls(tmp_path):
    from openhdo_server.integrations import IntegrationManager, DeviceAction, IntegrationView
    async def run():
        devices = IntegrationManager(tmp_path / "devices.sqlite3")
        class Demo:
            async def devices(self, config):
                return [{"external_id":"one", "name":"Socket", "kind":"cz", "product_name":"Demo socket", "updated_at":None, "available":True, "controls":[{"code":"switch", "name":"Power", "type":"Boolean", "constraints":{}}], "state":{"switch":config.get("on", False)}}]
            async def command(self, config, id, code, value): self.last = (id, code, value)
        provider = Demo(); devices.plugin_providers["example:demo"] = provider
        view = await devices.add_plugin("example:demo", "My home", {"on": True, "token": "private"})
        assert IntegrationView.model_validate(view).provider == "example:demo"
        assert "private" not in json.dumps(devices.integrations())
        device = devices.devices()[0]
        updated = await devices.add_plugin("example:demo", "Renamed home", {"on":False}, view["id"])
        assert updated["id"] == view["id"] and updated["name"] == "Renamed home"
        assert devices.devices()[0]["id"] == device["id"]
        await devices.action(device["id"], DeviceAction(code="switch", value=False))
        assert provider.last == ("one", "switch", False)
        await devices.close()
    asyncio.run(run())


def test_store_migration_is_atomic(tmp_path):
    from openhdo_plugin.context import Store
    store = Store(tmp_path / "state.sqlite3")
    store.set("name", "Before")
    with pytest.raises(ValueError): store.migrate(1, lambda state: {"invalid": float("nan")})
    assert store.get("name") == "Before"
    store.migrate(1, lambda state: {"title": state["name"]})
    store.migrate(1, lambda state: {"title": "Must not run twice"})
    assert store.get("title") == "Before"
    store.db.close()


def test_plugin_http_auth_csrf_routes_and_public_assets(tmp_path):
    from openhdo_server.app import create_app
    from openhdo_server.config import ServerSettings
    settings = ServerSettings(data_dir=str(tmp_path / "data"), auth_db_path=str(tmp_path / "auth.sqlite3"), api_token="plugin-test-token", admin_username="admin", admin_password="test-password")
    app = create_app(settings)
    folder = source(tmp_path / "src", code="def activate(ctx):\n    ctx.route('private', lambda request, ctx: {'ok':True})\n", permissions=["api"])
    (folder / "web").mkdir(); (folder / "web/icon.svg").write_text("<svg/>")
    package = pack(folder, tmp_path / "plugin.hdop")
    with TestClient(app) as client:
        assert client.get("/api/v1/plugins").status_code == 401
        token = {"Authorization":"Bearer plugin-test-token"}
        assert client.post("/api/v1/plugins/install", content=package.read_bytes(), headers=token).status_code == 200
        assert client.post("/api/v1/plugins/example/enable", headers=token).status_code == 200
        assert client.get("/api/v1/plugins/example/api/private", headers=token).json() == {"ok":True}
        assert client.get("/api/v1/plugins/example/assets/web/icon.svg", headers=token).status_code == 200
        assert client.get("/api/v1/plugins/example/assets/backend/plugin.py", headers=token).status_code == 404
        assert client.post("/api/v1/auth/login", json={"username":"admin","password":"test-password"}).status_code == 200
        assert client.post("/api/v1/plugins/example/disable").status_code == 403
        csrf = {"X-OpenHDO-CSRF":client.cookies.get("openhdo_csrf")}
        assert client.post("/api/v1/auth/register", json={"username":"viewer","password":"test-password"}).status_code == 201
        assert client.post("/api/v1/auth/login", json={"username":"viewer","password":"test-password"}).status_code == 200
        assert client.get("/api/v1/plugins/example/api/private").status_code == 403
        assert client.post("/api/v1/plugins/example/enable", headers={"X-OpenHDO-CSRF":client.cookies.get("openhdo_csrf")}).status_code == 403
