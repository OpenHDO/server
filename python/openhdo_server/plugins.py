"""Local plugin lifecycle, atomic .hdop installation and authenticated host API."""
from __future__ import annotations
import asyncio
import hashlib
import importlib.util
import inspect
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from openhdo_plugin import PluginContext, PluginError, unpack, validate_manifest
from openhdo_plugin.archive import MAX_PACKAGE_BYTES
from openhdo_plugin.manifest import safe_path
from openhdo_plugin.context import current_plugin
from .service import ServiceError


class ManagedProvider:
    def __init__(self, manager, owner, implementation):
        self.manager, self.owner, self.implementation = manager, owner, implementation

    async def devices(self, config):
        return await self.manager.invoke(self.owner, self.implementation.devices, config)

    @property
    def poll_interval(self):
        return min(300, max(5, getattr(self.implementation, 'poll_interval', 5)))

    @property
    def acknowledges_commands(self):
        return getattr(self.implementation, 'acknowledges_commands', False)

    async def command(self, config, external_id, code, value):
        return await self.command_batch(config, external_id, code, value, [])

    async def command_batch(self, config, external_id, code, value, preceding=None):
        if hasattr(self.implementation, 'command_batch'):
            return await self.manager.invoke(self.owner, self.implementation.command_batch, config, external_id, code, value, preceding or [])
        for command in preceding or []:
            await self.manager.invoke(self.owner, self.implementation.command, config, external_id, command['code'], command['value'])
        return await self.manager.invoke(self.owner, self.implementation.command, config, external_id, code, value)


class PluginManager:
    def __init__(self, data_dir, services=None):
        self.root = Path(data_dir) / "plugins"
        self.root.mkdir(parents=True, exist_ok=True)
        self.data = Path(data_dir) / "plugin-data"
        self.state_path = self.root / ".state.json"
        self.state = json.loads(self.state_path.read_text("utf-8")) if self.state_path.exists() else {}
        self.records, self.contexts, self.running, self.providers = {}, {}, {}, {}
        self.calls = {}
        self.services = services or {}
        self.services["extensions"] = self.extensions
        self.lock = asyncio.Lock()
        self.log = logging.getLogger("openhdo.plugins")
        self.events = asyncio.Queue(maxsize=1024)
        self.event_task = None

    def save(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2), "utf-8")
        tmp.replace(self.state_path)

    def scan(self):
        records = {}
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            try:
                if directory.is_symlink():
                    raise PluginError("Plugin directories cannot be symlinks")
                manifest = validate_manifest(json.loads((directory / "hdo.json").read_text("utf-8")))
                if manifest["id"] != directory.name:
                    raise PluginError("Directory name must match manifest id")
                for entry in manifest.get("entrypoints", {}).values():
                    path = directory / entry
                    if not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
                        raise PluginError("Entrypoint is missing or outside the plugin")
                revision = hashlib.sha256()
                for path in sorted(directory.rglob("*")):
                    if path.is_symlink():
                        raise PluginError("Plugin files cannot be symlinks")
                    if path.is_file() and "__pycache__" not in path.parts:
                        revision.update(path.relative_to(directory).as_posix().encode()); revision.update(path.read_bytes())
                records[directory.name] = {"manifest": manifest, "revision": revision.hexdigest()[:16], "status": "disabled", "error": None}
            except Exception as error:
                records[directory.name] = {"manifest": {"id": directory.name, "name": directory.name, "version": "?"}, "status": "invalid", "error": str(error)}
        self.records = records

    async def start(self):
        await asyncio.to_thread(self.scan)
        self.event_task = asyncio.create_task(self.event_loop())
        for id in list(self.records):
            if self.state.get(id, {}).get("enabled"):
                try:
                    await self.activate(id, [])
                except Exception as error:
                    self.log.warning("Plugin %s failed: %s", id, error)

    async def activate(self, id, stack):
        if id in self.contexts:
            return
        record = self.records.get(id)
        if not record or record["status"] == "invalid":
            raise PluginError(f"Missing or invalid dependency: {id}")
        if id in stack:
            raise PluginError("Cyclic plugin dependency")
        manifest = record["manifest"]
        try:
            for dep, major in manifest.get("dependencies", {}).items():
                target = self.records.get(dep)
                if not target or not self.state.get(dep, {}).get("enabled") or int(target["manifest"]["version"].split(".")[0]) != major:
                    raise PluginError(f"Enable compatible dependency {dep} (major {major}) first")
                await self.activate(dep, [*stack, id])
            context = PluginContext(manifest, self.data / id, self.services, self.emit)
            entry = manifest.get("entrypoints", {}).get("python")
            try:
                if entry:
                    module_name = "_hdo_plugin_" + id.replace("-", "_").replace(".", "_") + "_" + record["revision"]
                    spec = importlib.util.spec_from_file_location(module_name, self.root / id / entry, submodule_search_locations=[str((self.root / id / entry).parent)])
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    context.on_dispose(lambda: [sys.modules.pop(name, None) for name in list(sys.modules) if name == module_name or name.startswith(module_name + ".")])
                    # Compile from source: upgrades never reuse stale timestamp-based .pyc files.
                    exec(compile((self.root / id / entry).read_bytes(), str(self.root / id / entry), "exec"), module.__dict__)
                    result = module.activate(context)
                    if inspect.isawaitable(result):
                        result = await result
                    if callable(result):
                        context.on_dispose(result)
                declared = {p["id"] for p in manifest.get("contributes", {}).get("providers", [])}
                if set(context.providers) != declared:
                    raise PluginError("Declared and registered providers must match")
                self.contexts[id] = context
                for local, provider in context.providers.items():
                    self.providers[id + ":" + local] = ManagedProvider(self, id, provider)
                self.running[id] = [asyncio.create_task(factory(), name=f"plugin:{id}") for factory in context.tasks]
                for task in self.running[id]:
                    task.add_done_callback(lambda task, id=id: self.task_done(id, task))
                record.update(status="enabled", error=None)
            except Exception:
                await self.deactivate(id)
                if id not in self.contexts:
                    await context.close()
                raise
        except Exception as error:
            record.update(status="error", error=str(error))
            raise

    def task_done(self, id, task):
        if not task.cancelled() and task.exception():
            self.records[id].update(status="error", error="Background task failed; see server log")
            self.log.error("Plugin %s task failed", id, exc_info=task.exception())

    async def deactivate(self, id):
        if id in self.records:
            self.records[id]["status"] = "disabled"
        tasks = self.running.pop(id, [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        pending = list(self.calls.get(id, set()))
        if pending:
            _, unfinished = await asyncio.wait(pending, timeout=30)
            for task in unfinished:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        context = self.contexts.pop(id, None)
        for key in list(self.providers):
            if key.startswith(id + ":"):
                del self.providers[key]
        if context:
            try:
                await context.close()
            except Exception:
                self.log.exception("Plugin cleanup failed: %s", id)
        if id in self.records:
            self.records[id]["status"] = "disabled"

    async def close(self):
        if self.event_task:
            self.event_task.cancel()
            await asyncio.gather(self.event_task, return_exceptions=True)
        for id in reversed(list(self.contexts)):
            await self.deactivate(id)

    async def reload(self):
        async with self.lock:
            await self.close()
            await self.start()

    def dependent(self, id):
        return [key for key, context in self.contexts.items() if id in context.manifest.get("dependencies", {})]

    async def invoke(self, id, handler, *args):
        if id not in self.contexts or self.records[id]["status"] not in {"enabled", "error"}:
            raise ServiceError(503, "plugin_disabled", "Plugin is disabled")
        async def run():
            token = current_plugin.set(id)
            try:
                result = handler(*args)
                return await result if inspect.isawaitable(result) else result
            finally:
                current_plugin.reset(token)
        task = asyncio.create_task(run())
        calls = self.calls.setdefault(id, set())
        calls.add(task)
        try:
            return await task
        finally:
            calls.discard(task)

    def extensions(self, kind):
        return {context.id + ":" + local: implementation for context in self.contexts.values()
                for (registered_kind, local), implementation in context.registrations.items() if kind == registered_kind}

    async def enable(self, id, enabled):
        async with self.lock:
            if id not in self.records:
                raise PluginError("Plugin not found")
            if enabled:
                if id in self.contexts and self.records[id]["status"] == "error":
                    if self.dependent(id):
                        raise PluginError("Disable dependent plugins before restarting")
                    await self.deactivate(id)
                await self.activate(id, [])
            else:
                if self.dependent(id):
                    raise PluginError("Disable dependent plugins first: " + ", ".join(self.dependent(id)))
                await self.deactivate(id)
            self.state.setdefault(id, {})["enabled"] = enabled
            self.save()

    async def install(self, package):
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix=".install-", dir=self.root) as staging:
                stage = Path(staging) / "plugin"
                manifest = await asyncio.to_thread(unpack, package, stage)
                id = manifest["id"]
                if self.dependent(id):
                    raise PluginError("Disable dependent plugins before updating")
                target, backup = self.root / id, Path(staging) / "backup"
                enabled = id in self.contexts
                old_records = self.records.copy()
                await self.deactivate(id)
                if target.exists():
                    target.rename(backup)
                try:
                    stage.rename(target)
                    await asyncio.to_thread(self.scan)
                    if enabled:
                        await self.activate(id, [])
                except Exception:
                    await self.deactivate(id)
                    if target.exists():
                        shutil.rmtree(target)
                    if backup.exists():
                        backup.rename(target)
                    self.records = old_records
                    if enabled:
                        await self.activate(id, [])
                    raise
                # Preserve statuses for unaffected active plugins after the inventory scan.
                for key in self.contexts:
                    self.records[key]["status"] = old_records.get(key, {}).get("status", "enabled") if key != id else "enabled"
                self.save()
                return id

    async def remove(self, id):
        async with self.lock:
            if id not in self.records:
                raise PluginError("Plugin not found")
            if self.dependent(id):
                raise PluginError("Disable dependent plugins first")
            await self.deactivate(id)
            target = self.root / id
            if not target.resolve().is_relative_to(self.root.resolve()) or target.is_symlink():
                raise PluginError("Unsafe plugin directory")
            shutil.rmtree(target)
            self.records.pop(id)
            self.state.pop(id, None)
            self.save()

    async def emit(self, event, payload, source=None):
        # Never call plugin handlers inside device/SQLite locks. Bounded delivery keeps
        # a slow automation from growing memory or blocking a device command.
        try:
            self.events.put_nowait((event, payload, source or current_plugin.get()))
        except asyncio.QueueFull:
            self.log.warning("Plugin event queue full; dropping %s", event)

    async def event_loop(self):
        while True:
            event, payload, source = await self.events.get()
            await self.dispatch_event(event, payload, source)

    async def dispatch_event(self, event, payload, source):
        # Snapshot allows handlers to register other hooks without mutating iteration.
        for context in list(self.contexts.values()):
            for handler in list(context.hooks.get(event, [])):
                try:
                    await asyncio.wait_for(self.invoke(context.id, handler, {"type": event, "source": source, "payload": payload}), timeout=30)
                except Exception:
                    context.log.exception("Event handler failed: %s", event)

    def asset(self, id, relative):
        if id not in self.contexts:
            raise PluginError("Plugin is disabled")
        root = (self.root / id).resolve()
        path = root.joinpath(*safe_path(relative).parts).resolve()
        # Only public assets are served: never Python sources, manifests or private files.
        if not relative.startswith("web/") or path.suffix not in {".js", ".css", ".json", ".svg", ".png", ".webp", ".woff2"} or not path.is_relative_to(root) or not path.is_file():
            raise PluginError("Asset not found")
        return path


def plugin_router(manager, require_user, require_admin, require_csrf):
    router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])
    read = [Depends(require_user)]
    admin = [Depends(require_admin), Depends(require_csrf)]

    @router.get("", dependencies=read)
    async def inventory():
        return {"apiVersion": 1, "plugins": list(manager.records.values())}

    @router.post("/install", dependencies=admin)
    async def install(request: Request):
        # Raw upload avoids multipart buffering/dependencies and bounds memory/disk usage.
        with tempfile.TemporaryDirectory(prefix=".upload-", dir=manager.root) as temporary:
            package = Path(temporary) / "package.hdop"
            size = 0
            with package.open("wb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_PACKAGE_BYTES:
                        raise ServiceError(413, "plugin_too_large", "Plugin exceeds 64 MiB")
                    stream.write(chunk)
            try:
                return {"id": await manager.install(package)}
            except Exception as error:
                manager.log.warning("Plugin installation rejected: %s", error)
                raise ServiceError(422, "plugin_install_failed", str(error)) from None

    @router.post("/providers/{provider}/connect", dependencies=admin)
    async def connect(provider: str, request: Request):
        value = await request.json()
        if not isinstance(value, dict):
            raise ServiceError(422, "invalid_value", "Expected provider configuration")
        return await manager.services["devices"].add_plugin(provider, value.get("name"), value.get("config"), value.get("integration_id"))

    @router.post("/reload", dependencies=admin)
    async def reload():
        await manager.reload()
        return {"plugins": list(manager.records.values())}

    @router.post("/{id}/enable", dependencies=admin)
    async def enable(id: str):
        try:
            await manager.enable(id, True)
        except Exception as error:
            raise ServiceError(409, "plugin_activation_failed", str(error)) from None
        return {"id": id, "enabled": True}

    @router.post("/{id}/disable", dependencies=admin)
    async def disable(id: str):
        try:
            await manager.enable(id, False)
        except PluginError as error:
            raise ServiceError(409, "plugin_dependency", str(error)) from None
        return {"id": id, "enabled": False}

    @router.delete("/{id}", dependencies=admin, status_code=204)
    async def remove(id: str):
        try:
            await manager.remove(id)
        except PluginError as error:
            raise ServiceError(409, "plugin_remove_failed", str(error)) from None
        return Response(status_code=204)

    @router.get("/{id}/assets/{path:path}", dependencies=read)
    async def asset(id: str, path: str):
        try:
            return FileResponse(manager.asset(id, path), headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})
        except PluginError as error:
            raise ServiceError(404, "plugin_asset_missing", str(error)) from None

    @router.api_route("/{id}/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], dependencies=[Depends(require_user), Depends(require_csrf)])
    async def dispatch(id: str, path: str, request: Request):
        context = manager.contexts.get(id)
        route = context.routes.get((request.method, path)) if context else None
        if not route:
            raise ServiceError(404, "plugin_route_missing", "Plugin route not found")
        role, handler = route
        if role == "admin":
            await require_admin(request)
        return await manager.invoke(id, handler, request, context)

    return router
