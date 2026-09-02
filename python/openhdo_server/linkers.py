"""Persistent admin-side Linker registrations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import RLock

from pydantic import TypeAdapter, ValidationError

from .models import Identifier, LinkManifest


class LinkerRegistryConflict(Exception):
    """The requested Linker registration conflicts with existing data."""


@dataclass(frozen=True)
class LinkerEntry:
    id: str
    name: str
    manifest: LinkManifest | None = None


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

    def add(self, linker_id: str, name: str) -> LinkerEntry:
        with self._lock:
            if linker_id in self._entries:
                raise LinkerRegistryConflict("linker is already registered")
            entry = LinkerEntry(id=linker_id, name=name)
            self._entries[linker_id] = entry
            self._save()
            return entry

    def update_manifest(self, manifest: LinkManifest) -> None:
        with self._lock:
            current = self._entries.get(manifest.id)
            if current is None:
                return
            self._entries[manifest.id] = LinkerEntry(id=manifest.id, name=manifest.name, manifest=manifest)
            self._save()

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
            self._entries[linker_id] = LinkerEntry(id=linker_id, name=name, manifest=manifest)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "linkers": [
                        {
                            "id": entry.id,
                            "name": entry.name,
                            "manifest": entry.manifest.model_dump(mode="json") if entry.manifest else None,
                        }
                        for entry in sorted(self._entries.values(), key=lambda item: item.id)
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
            id=entry.id,
            name=entry.name,
            manifest=entry.manifest.model_copy(deep=True) if entry.manifest else None,
        )
