"""In-memory canonical Light repository."""

from __future__ import annotations

from datetime import datetime
from threading import RLock

from .models import DeviceManifest, LightRecord, LightState, LinkManifest


class RepositoryError(Exception):
    """Base class for repository boundary errors."""

    code = "repository_error"


class LightNotFound(RepositoryError):
    code = "light_not_found"


class LinkerConflict(RepositoryError):
    code = "linker_conflict"


class StaleState(RepositoryError):
    code = "stale_state"


class InMemoryLightRepository:
    """Store canonical abstract Light inventory and state for one process."""

    def __init__(self, clock) -> None:
        self._clock = clock
        self._lights: dict[str, LightRecord] = {}
        self._linkers: dict[str, LinkManifest] = {}
        self._lock = RLock()

    def list_lights(self) -> list[LightRecord]:
        with self._lock:
            return [self._copy(record) for record in sorted(self._lights.values(), key=lambda item: item.light_id)]

    def get_light(self, light_id: str) -> LightRecord:
        with self._lock:
            record = self._lights.get(light_id)
            if record is None:
                raise LightNotFound("light is not registered")
            return self._copy(record)

    def register_linker(self, linker_id: str, manifest: LinkManifest) -> list[LightRecord]:
        if manifest.id != linker_id:
            raise LinkerConflict("linker path id does not match manifest id")
        devices = manifest.devices or []
        with self._lock:
            self._validate_registration(linker_id, devices)
            self._linkers[linker_id] = manifest
            registered: list[LightRecord] = []
            for device in devices:
                capability = device.capabilities[0]
                previous = self._lights.get(device.id)
                record = LightRecord(
                    light_id=device.id,
                    name=device.name,
                    linker_id=linker_id,
                    capability=capability,
                    state=None if previous is None else previous.state,
                    updated_at=None if previous is None else previous.updated_at,
                )
                self._lights[device.id] = record
                registered.append(self._copy(record))
            return registered

    def apply_state(self, linker_id: str, state: LightState) -> tuple[LightRecord, bool]:
        with self._lock:
            record = self._lights.get(state.light_id)
            if record is None:
                raise LightNotFound("light is not registered")
            if record.linker_id != linker_id:
                raise LinkerConflict("light belongs to another linker")
            if record.state is not None and state.state_revision < record.state.state_revision:
                raise StaleState("state revision is older than the canonical state")
            changed = record.state != state
            updated_at: datetime = self._clock() if changed else record.updated_at or self._clock()
            updated = record.model_copy(update={"state": state, "updated_at": updated_at})
            self._lights[state.light_id] = updated
            return self._copy(updated), changed

    def linker_registered(self, linker_id: str) -> bool:
        with self._lock:
            return linker_id in self._linkers

    def _validate_registration(self, linker_id: str, devices: list[DeviceManifest]) -> None:
        seen: set[str] = set()
        for device in devices:
            if device.id in seen:
                raise LinkerConflict("manifest contains duplicate device ids")
            seen.add(device.id)
            previous = self._lights.get(device.id)
            if previous is not None and previous.linker_id != linker_id:
                raise LinkerConflict("device is already owned by another linker")

    @staticmethod
    def _copy(record: LightRecord) -> LightRecord:
        return record.model_copy(deep=True)
