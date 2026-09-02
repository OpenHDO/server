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
    DiscoveryCandidateEnvelope,
    DiscoveryCompletedEnvelope,
    DiscoverySessionResponse,
    DiscoveryStartEnvelope,
    DiscoveryStartRequest,
    LightCommandEnvelope,
    LightRecord,
    LightStateReportedEnvelope,
    LightUpdatedEnvelope,
    LinkManifest,
    LinkRegisterEnvelope,
    LinkerEnvelope,
    utc_now,
)
from .repository import (
    InMemoryDiscoverySessionRepository,
    InMemoryLightRepository,
    DiscoverySessionConflict,
    DiscoverySessionNotFound,
    LightNotFound,
    LinkerConflict,
    RepositoryError,
    StaleState,
)


class CommandTransport(Protocol):
    async def send(self, linker_id: str, message: LightCommandEnvelope) -> bool: ...


class DiscoveryTransport(Protocol):
    async def send(self, linker_id: str, message: DiscoveryStartEnvelope) -> bool: ...


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

    def list_linkers(self) -> list[LinkManifest]:
        return self.repository.list_linkers()

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


class DiscoveryService:
    """Coordinate bounded, process-local discovery sessions."""

    def __init__(
        self,
        repository: InMemoryDiscoverySessionRepository,
        transport: DiscoveryTransport,
        instance_name: str,
        logger: logging.Logger,
        clock: Callable = utc_now,
    ) -> None:
        self.repository = repository
        self._transport = transport
        self._instance_name = instance_name
        self._logger = logger
        self._clock = clock
        self._timeouts: dict[UUID, asyncio.Task[None]] = {}

    async def start(self, request: DiscoveryStartRequest) -> DiscoverySessionResponse:
        session_id = uuid4()
        start_id = uuid4()
        start = DiscoveryStartEnvelope(
            v=1,
            id=start_id,
            type="discovery.start",
            ts=self._clock(),
            source=self._instance_name,
            correlation_id=start_id,
            payload={"session_id": session_id, "timeout_s": request.timeout_s},
        )
        self.repository.create(session_id, request.linker_id, start.id)
        try:
            sent = await self._transport.send(request.linker_id, start)
        except Exception:
            sent = False
        if not sent:
            self.repository.finish(
                session_id,
                "failed",
                "the linker is not connected or could not receive discovery.start",
            )
            await self.linker_disconnected(request.linker_id)
            log_event(
                self._logger,
                logging.WARNING,
                "discovery.failed",
                {"session_id": str(session_id), "linker_id": request.linker_id, "error": "linker_unavailable"},
            )
        else:
            if self.repository.get(session_id)[1].status == "running":
                self._timeouts[session_id] = asyncio.create_task(
                    self._expire(session_id, request.timeout_s),
                    name=f"discovery-timeout-{session_id}",
                )
            log_event(
                self._logger,
                logging.INFO,
                "discovery.started",
                {"session_id": str(session_id), "linker_id": request.linker_id, "timeout_s": request.timeout_s},
            )
        return self.get(session_id)

    def get(self, session_id: UUID) -> DiscoverySessionResponse:
        try:
            return self.repository.get(session_id)[1]
        except DiscoverySessionNotFound as error:
            raise ServiceError(404, error.code, str(error)) from error

    async def ingest_candidate(self, linker_id: str, message: DiscoveryCandidateEnvelope) -> None:
        self._require_linker_source(linker_id, message)
        _, session = self._matching_session(linker_id, message.correlation_id, message.payload.session_id)
        try:
            self.repository.add_candidate(session.session_id, message.payload)
        except DiscoverySessionConflict as error:
            raise ServiceError(409, "discovery_session_closed", str(error)) from error
        log_event(
            self._logger,
            logging.INFO,
            "discovery.candidate",
            {"session_id": str(session.session_id), "linker_id": linker_id, "candidate_id": message.payload.candidate_id},
        )

    async def ingest_completed(self, linker_id: str, message: DiscoveryCompletedEnvelope) -> None:
        self._require_linker_source(linker_id, message)
        _, session = self._matching_session(linker_id, message.correlation_id, message.payload.session_id)
        error = message.payload.error
        if message.payload.status == "failed" and error is None:
            error = "linker reported discovery failure"
        finished = self.repository.finish(session.session_id, message.payload.status, error)
        self._cancel_timeout(session.session_id)
        if finished:
            log_event(
                self._logger,
                logging.INFO if message.payload.status == "completed" else logging.WARNING,
                "discovery.completed",
                {
                    "session_id": str(session.session_id),
                    "linker_id": linker_id,
                    "status": message.payload.status,
                },
            )

    async def close(self) -> None:
        tasks = tuple(self._timeouts.values())
        self._timeouts.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def linker_disconnected(self, linker_id: str) -> None:
        session_ids = self.repository.fail_running_for_linker(linker_id, "linker disconnected")
        for session_id in session_ids:
            self._cancel_timeout(session_id)
        if session_ids:
            log_event(
                self._logger,
                logging.WARNING,
                "discovery.linker_disconnected",
                {"linker_id": linker_id, "session_count": len(session_ids)},
            )

    async def _expire(self, session_id: UUID, timeout_s: int) -> None:
        try:
            await asyncio.sleep(timeout_s)
            try:
                _, session = self.repository.get(session_id)
                finished = self.repository.finish(session_id, "failed", "discovery timed out")
            except DiscoverySessionNotFound:
                return
            if finished:
                log_event(
                    self._logger,
                    logging.WARNING,
                    "discovery.timeout",
                    {"session_id": str(session.session_id), "linker_id": session.linker_id},
                )
        except asyncio.CancelledError:
            raise
        finally:
            if self._timeouts.get(session_id) is asyncio.current_task():
                self._timeouts.pop(session_id, None)

    def _matching_session(
        self, linker_id: str, correlation_id: UUID, session_id: UUID
    ) -> tuple[UUID, DiscoverySessionResponse]:
        try:
            expected_correlation, session = self.repository.get(session_id)
        except DiscoverySessionNotFound as error:
            raise ServiceError(409, "unknown_discovery_session", str(error)) from error
        if session.linker_id != linker_id:
            raise ServiceError(403, "linker_mismatch", "discovery session belongs to another linker")
        if correlation_id != expected_correlation:
            raise ServiceError(
                409,
                "correlation_mismatch",
                "discovery message correlation does not match discovery.start",
            )
        return expected_correlation, session

    @staticmethod
    def _require_linker_source(linker_id: str, message: DiscoveryCandidateEnvelope | DiscoveryCompletedEnvelope) -> None:
        if message.source != linker_id:
            raise ServiceError(403, "source_mismatch", "message source does not match the linker connection")

    def _cancel_timeout(self, session_id: UUID) -> None:
        task = self._timeouts.pop(session_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
