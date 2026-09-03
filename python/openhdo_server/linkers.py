"""Persistent admin-side Linker registrations."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from .models import DeviceManifest, Identifier, LinkManifest


class LinkerRegistryConflict(Exception):
    """The requested Linker registration conflicts with existing data."""


class LinkerRegistryNotFound(Exception):
    """The requested Linker registration does not exist."""


@dataclass(frozen=True)
class LinkerEntry:
    key: str
    id: str
    name: str
    host: str | None = None
    port: int | None = None
    secret: str | None = None
    manifest: LinkManifest | None = None
    name_override: str | None = None


class LinkerRegistry:
    """Keep admin registrations and the latest real Linker manifest."""

    def __init__(self, data_path: str | Path) -> None:
        self._path = Path(data_path)
        self._entries: dict[str, LinkerEntry] = {}
        self._lock = RLock()
        self._load()

    def list(self) -> list[LinkerEntry]:
        with self._lock:
            return [self._copy(entry) for entry in sorted(self._entries.values(), key=lambda item: item.id)]

    def connection_entries(self) -> list[LinkerEntry]:
        with self._lock:
            return [
                self._copy(entry)
                for entry in sorted(self._entries.values(), key=lambda item: item.key)
                if entry.host is not None and entry.port is not None and entry.secret is not None
            ]

    def is_registered(self, linker_id: str) -> bool:
        with self._lock:
            return any(entry.id == linker_id for entry in self._entries.values())

    def add(self, linker_id: str, name: str) -> LinkerEntry:
        with self._lock:
            if any(entry.id == linker_id for entry in self._entries.values()):
                raise LinkerRegistryConflict("linker is already registered")
            entry = LinkerEntry(key=linker_id, id=linker_id, name=name)
            self._entries[entry.key] = entry
            self._save()
            return entry

    def add_connection(self, host: str, port: int, secret: str) -> LinkerEntry:
        with self._lock:
            if any(entry.host == host and entry.port == port for entry in self._entries.values()):
                raise LinkerRegistryConflict("linker endpoint is already registered")
            key = f"linker.{uuid4().hex}"
            entry = LinkerEntry(
                key=key,
                id=key,
                name=f"{host}:{port}",
                host=host,
                port=port,
                secret=secret,
            )
            self._entries[entry.key] = entry
            self._save()
            return entry

    def update_manifest(self, manifest: LinkManifest, key: str | None = None) -> None:
        with self._lock:
            entry_key = key or next(
                (entry.key for entry in self._entries.values() if entry.id == manifest.id),
                None,
            )
            current = self._entries.get(entry_key) if entry_key else None
            if current is None:
                return
            if any(entry.key != current.key and entry.id == manifest.id for entry in self._entries.values()):
                raise LinkerRegistryConflict("linker identity is already registered")
            if manifest.devices is None and current.manifest is not None:
                manifest = manifest.model_copy(update={"devices": current.manifest.devices})
            self._entries[current.key] = LinkerEntry(
                key=current.key,
                id=manifest.id,
                name=current.name_override or manifest.name,
                host=current.host,
                port=current.port,
                secret=current.secret,
                manifest=manifest,
                name_override=current.name_override,
            )
            self._save()

    def add_manifest_device(self, linker_id: str, device: DeviceManifest) -> None:
        with self._lock:
            current = next((entry for entry in self._entries.values() if entry.id == linker_id), None)
            if current is None or current.manifest is None or any(
                item.id == device.id for item in (current.manifest.devices or [])
            ):
                return
            self.update_manifest(
                current.manifest.model_copy(update={"devices": [*(current.manifest.devices or []), device]}),
                key=current.key,
            )

    def rename(self, linker_id: str, name: str) -> LinkerEntry:
        with self._lock:
            current = next((entry for entry in self._entries.values() if entry.id == linker_id), None)
            if current is None:
                raise LinkerRegistryNotFound("linker is not registered")
            renamed = LinkerEntry(
                key=current.key,
                id=current.id,
                name=name,
                host=current.host,
                port=current.port,
                secret=current.secret,
                manifest=current.manifest,
                name_override=name,
            )
            self._entries[current.key] = renamed
            self._save()
            return self._copy(renamed)

    def delete(self, linker_id: str) -> LinkerEntry:
        with self._lock:
            key = next((entry.key for entry in self._entries.values() if entry.id == linker_id), None)
            if key is None:
                raise LinkerRegistryNotFound("linker is not registered")
            entry = self._entries.pop(key)
            self._save()
            return self._copy(entry)

    def _load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        for raw_entry in payload.get("linkers", []):
            if not isinstance(raw_entry, dict):
                continue
            linker_id = raw_entry.get("id")
            name = raw_entry.get("name")
            if not isinstance(linker_id, str) or not isinstance(name, str):
                continue
            try:
                TypeAdapter(Identifier).validate_python(linker_id)
            except ValidationError:
                continue
            manifest = None
            if isinstance(raw_entry.get("manifest"), dict):
                try:
                    manifest = LinkManifest.model_validate(raw_entry["manifest"])
                except ValidationError:
                    continue
            key = raw_entry.get("key", linker_id)
            name_override = raw_entry.get("name_override")
            host = raw_entry.get("host")
            port = raw_entry.get("port")
            secret = raw_entry.get("secret", raw_entry.get("minisecret"))
            if not isinstance(key, str) or not key:
                continue
            if host is not None or port is not None or secret is not None:
                if (
                    not isinstance(host, str)
                    or not isinstance(port, int)
                    or isinstance(port, bool)
                    or not 1 <= port <= 65535
                    or not isinstance(secret, str)
                    or not secret
                ):
                    continue
                try:
                    host = str(ip_address(host))
                except ValueError:
                    continue
            self._entries[key] = LinkerEntry(
                key=key,
                id=linker_id,
                name=name,
                host=host,
                port=port,
                secret=secret,
                manifest=manifest,
                name_override=name_override if isinstance(name_override, str) and name_override else None,
            )

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "linkers": [
                        {
                            "key": entry.key,
                            "id": entry.id,
                            "name": entry.name,
                            "host": entry.host,
                            "port": entry.port,
                            "secret": entry.secret,
                            "name_override": entry.name_override,
                            "manifest": entry.manifest.model_dump(mode="json") if entry.manifest else None,
                        }
                        for entry in sorted(self._entries.values(), key=lambda item: item.key)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _copy(entry: LinkerEntry) -> LinkerEntry:
        return LinkerEntry(
            key=entry.key,
            id=entry.id,
            name=entry.name,
            host=entry.host,
            port=entry.port,
            secret=entry.secret,
            manifest=entry.manifest.model_copy(deep=True) if entry.manifest else None,
            name_override=entry.name_override,
        )
