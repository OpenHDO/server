"""Capability-oriented host API; registrations are owned and disposed by the runtime."""
import asyncio
import json
import logging
import sqlite3
from contextvars import ContextVar
from typing import Protocol, Any
from .types import DeviceSnapshot

current_plugin = ContextVar("hdo_current_plugin", default="host")


class Provider(Protocol):
    async def devices(self, config: dict) -> list[DeviceSnapshot]: ...
    async def command(self, config: dict, external_id: str, code: str, value: Any) -> None: ...


class Store:
    """Transactional JSON key/value store, private to one plugin and retained on upgrades."""
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        encoded = json.dumps(value, allow_nan=False)
        with self.db:
            self.db.execute("INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, encoded))

    def delete(self, key):
        with self.db:
            self.db.execute("DELETE FROM state WHERE key=?", (key,))

    def migrate(self, version, transform):
        """Atomically transform all JSON state once. transform(dict) returns a new dict."""
        if type(version) is not int or version < 1:
            raise ValueError("Migration version must be a positive integer")
        current = self.get("__hdo_schema__", 0)
        if current >= version:
            return
        with self.db:
            snapshot = {key: json.loads(value) for key, value in self.db.execute("SELECT key,value FROM state") if key != "__hdo_schema__"}
            updated = transform(snapshot)
            if not isinstance(updated, dict) or any(not isinstance(key, str) or key == "__hdo_schema__" for key in updated):
                raise ValueError("Migration must return a JSON state mapping")
            encoded = [(key, json.dumps(value, allow_nan=False)) for key, value in updated.items()]
            self.db.execute("DELETE FROM state")
            self.db.executemany("INSERT INTO state VALUES (?,?)", [*encoded, ("__hdo_schema__", str(version))])


class PluginContext:
    def __init__(self, manifest, data_dir, services, bus):
        self.manifest = manifest
        self.id = manifest["id"]
        self.data_dir = data_dir
        self.log = logging.getLogger("openhdo.plugin." + self.id)
        self._services, self._bus = services, bus
        self._store = None
        self._closed = False
        self.providers, self.routes, self.hooks, self.tasks, self.disposers, self.registrations = {}, {}, {}, [], [], {}

    def require(self, permission):
        if permission not in self.manifest.get("permissions", []):
            raise PermissionError(f"Declare the {permission} capability in hdo.json")

    @property
    def store(self):
        self.require("storage")
        if self._store is None:
            self._store = Store(self.data_dir / "state.sqlite3")
        return self._store

    def service(self, name):
        """Access documented host services (devices, HTTP) without importing server internals."""
        self.require("providers" if name == "devices" else "network")
        return self._services[name]

    def provider(self, id, implementation):
        self.require("providers")
        if id in self.providers:
            raise ValueError("Duplicate provider")
        self.providers[id] = implementation

    def extension(self, kind, id, implementation):
        """Register server-side flow nodes, device models, settings or other declared extensions."""
        declared = self.manifest.get("contributes", {}).get(kind, [])
        if not any(item["id"] == id for item in declared):
            raise ValueError("Declare extensions in hdo.json before registering them")
        key = (kind, id)
        if key in self.registrations:
            raise ValueError("Duplicate extension")
        self.registrations[key] = implementation

    def extensions(self, kind):
        """Return namespaced implementations currently registered by enabled plugins."""
        return self._services["extensions"](kind)

    def route(self, path, handler, *, methods=("GET",), role="admin"):
        """handler(request, context) -> JSON. Host enforces authentication and CSRF."""
        self.require("api")
        if role not in {"admin", "user"} or not path or path.startswith("/") or ".." in path:
            raise ValueError("Invalid route or role")
        for method in methods:
            key = (method.upper(), path)
            if key in self.routes:
                raise ValueError("Duplicate route")
            self.routes[key] = (role, handler)

    def on(self, event, handler):
        self.require("events")
        self.hooks.setdefault(event, []).append(handler)

    async def emit(self, event, payload):
        self.require("events")
        await self._bus(event, payload, self.id)

    def task(self, coroutine_factory):
        """Factory starts only after activation commits; canceled and awaited on disable."""
        self.require("tasks")
        self.tasks.append(coroutine_factory)

    def on_dispose(self, handler):
        self.disposers.append(handler)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        errors = []
        for handler in reversed(self.disposers):
            try:
                result = handler()
                if asyncio.iscoroutine(result):
                    await asyncio.wait_for(result, timeout=10)
            except Exception as error:
                errors.append(error)
        if self._store:
            self._store.db.close()
        if errors:
            raise errors[0]
