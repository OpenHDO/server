"""Application service for canonical Light registration and control."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Protocol
from uuid import UUID, uuid4

from .connections import LightEventHub
from .logging import log_event
from .models import (
    CommandResultEnvelope,
    CommandResultPayload,
    LightCommandEnvelope,
    LightRecord,
    LightStateReportedEnvelope,
    LightUpdatedEnvelope,
    LinkRegisterEnvelope,
    LinkerEnvelope,
    utc_now,
)
from .repository import (
    InMemoryLightRepository,
    LightNotFound,
    LinkerConflict,
    RepositoryError,
    StaleState,
)


class CommandTransport(Protocol):
    async def send(self, linker_id: str, message: LightCommandEnvelope) -> bool: ...


class ServiceError(Exception):
    """An expected application boundary failure."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class LightService:
    """Coordinate repository state, Linker messages, and update observers."""

    def __init__(
        self,
        repository: InMemoryLightRepository,
        transport: CommandTransport,
        events: LightEventHub,
        instance_name: str,
        logger: logging.Logger,
        clock: Callable = utc_now,
    ) -> None:
        self.repository = repository
        self._transport = transport
        self._events = events
        self._instance_name = instance_name
        self._logger = logger
        self._clock = clock
        self._pending: dict[UUID, LightCommandEnvelope] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, CommandResultEnvelope]] = {}
        # ponytail: one process-local lock; use keyed locks only if command throughput requires it.
        self._command_lock = asyncio.Lock()

    def list_lights(self) -> list[LightRecord]:
        return self.repository.list_lights()

    def get_light(self, light_id: str) -> LightRecord:
        try:
            return self.repository.get_light(light_id)
        except LightNotFound as error:
            raise ServiceError(404, error.code, str(error)) from error

    async def register_linker(self, linker_id: str, message: LinkRegisterEnvelope) -> None:
        self._require_linker_source(linker_id, message)
        try:
            records = self.repository.register_linker(linker_id, message.payload)
        except RepositoryError as error:
            raise ServiceError(409, error.code, str(error)) from error
        for record in records:
            await self._publish_update(record)
        log_event(
            self._logger,
            logging.INFO,
            "linker.registered",
            {"linker_id": linker_id, "device_count": len(records)},
        )

    async def ingest_state(self, linker_id: str, message: LightStateReportedEnvelope) -> None:
        self._require_linker_source(linker_id, message)
        try:
            record, changed = self.repository.apply_state(linker_id, message.payload)
        except LightNotFound as error:
            raise ServiceError(404, error.code, str(error)) from error
        except LinkerConflict as error:
            raise ServiceError(403, error.code, str(error)) from error
        except StaleState as error:
            raise ServiceError(409, error.code, str(error)) from error
        if changed:
            await self._publish_update(record, message.correlation_id)
        log_event(
            self._logger,
            logging.INFO,
            "light.state_received",
            {"linker_id": linker_id, "light_id": record.light_id, "changed": changed},
        )

    async def submit_command(self, command: LightCommandEnvelope) -> CommandResultEnvelope:
        async with self._command_lock:
            try:
                record = self.repository.get_light(command.payload.light_id)
            except LightNotFound as error:
                raise ServiceError(404, error.code, str(error)) from error

            key = (record.light_id, command.payload.idempotency_key)
            fingerprint = self._fingerprint(command)
            previous = self._idempotency.get(key)
            if previous is not None:
                if previous[0] != fingerprint:
                    raise ServiceError(409, "idempotency_conflict", "idempotency key was used for another command")
                return previous[1]

            forwarded = command.model_copy(update={"source": self._instance_name})
            result = CommandResultEnvelope(
                v=1,
                id=uuid4(),
                type="command.result",
                ts=self._clock(),
                source=self._instance_name,
                correlation_id=forwarded.id,
                payload=CommandResultPayload(
                    status="accepted",
                    light_id=record.light_id,
                    command_id=command.payload.command_id,
                    idempotency_key=command.payload.idempotency_key,
                ),
            )
            self._pending[command.payload.command_id] = forwarded
            self._idempotency[key] = (fingerprint, result)
            try:
                sent = await self._transport.send(record.linker_id, forwarded)
            except Exception as error:
                self._pending.pop(command.payload.command_id, None)
                self._idempotency.pop(key, None)
                raise ServiceError(503, "linker_unavailable", "the light's linker could not receive the command") from error
            if not sent:
                self._pending.pop(command.payload.command_id, None)
                self._idempotency.pop(key, None)
                raise ServiceError(503, "linker_unavailable", "the light's linker is not connected")

            log_event(
                self._logger,
                logging.INFO,
                "light.command_accepted",
                {
                    "light_id": record.light_id,
                    "linker_id": record.linker_id,
                    "command_id": str(command.payload.command_id),
                    "correlation_id": str(forwarded.id),
                },
            )
            return result

    async def ingest_result(self, linker_id: str, message: CommandResultEnvelope) -> None:
        self._require_linker_source(linker_id, message)
        command = self._pending.get(message.payload.command_id)
        if command is None:
            raise ServiceError(409, "unknown_command", "command result does not match a pending command")
        if message.correlation_id != command.id:
            raise ServiceError(409, "correlation_mismatch", "command result correlation does not match the command")
        if (
            message.payload.light_id != command.payload.light_id
            or message.payload.idempotency_key != command.payload.idempotency_key
        ):
            raise ServiceError(409, "command_mismatch", "command result does not match the pending command")

        key = (command.payload.light_id, command.payload.idempotency_key)
        if message.payload.status == "applied" and message.payload.state is not None:
            try:
                record, changed = self.repository.apply_state(linker_id, message.payload.state)
            except (LightNotFound, LinkerConflict, StaleState) as error:
                raise ServiceError(409, getattr(error, "code", "state_rejected"), str(error)) from error
            if changed:
                await self._publish_update(record, message.correlation_id)

        self._idempotency[key] = (self._fingerprint(command), message)
        if message.payload.status != "accepted":
            del self._pending[message.payload.command_id]
        log_event(
            self._logger,
            logging.INFO,
            "light.command_result",
            {
                "linker_id": linker_id,
                "light_id": message.payload.light_id,
                "command_id": str(message.payload.command_id),
                "status": message.payload.status,
            },
        )

    async def _publish_update(self, record: LightRecord, correlation_id: UUID | None = None) -> None:
        event = LightUpdatedEnvelope(
            v=1,
            id=uuid4(),
            type="light.updated",
            ts=self._clock(),
            source=self._instance_name,
            correlation_id=correlation_id,
            payload=record,
        )
        await self._events.publish(event)

    @staticmethod
    def _fingerprint(command: LightCommandEnvelope) -> str:
        return json.dumps(
            {"type": command.type, "payload": command.payload.model_dump(mode="json", exclude={"command_id"})},
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _require_linker_source(linker_id: str, message: LinkerEnvelope) -> None:
        if message.source != linker_id:
            raise ServiceError(403, "source_mismatch", "message source does not match the linker connection")
