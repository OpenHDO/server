"""Outbound WebSocket client for configured Linkers."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .linkers import LinkerEntry, LinkerRegistry
from .logging import log_event


class OutboundLinkerSocket:
    """Adapt the websockets client to the server's JSON socket interface."""

    def __init__(self, socket) -> None:
        self._socket = socket

    async def receive_json(self):
        try:
            message = await self._socket.recv()
        except ConnectionClosed as error:
            raise WebSocketDisconnect(code=error.code, reason=error.reason) from error
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        return json.loads(message)

    async def send_json(self, message: object) -> None:
        await self._socket.send(json.dumps(message, ensure_ascii=False, separators=(",", ":")))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        await self._socket.close(code=code, reason=reason)


class LinkerConnector:
    """Connect to every configured Linker and reconnect after disconnects."""

    def __init__(self, registry: LinkerRegistry, handler: Callable[[LinkerEntry, OutboundLinkerSocket], Awaitable[None]], logger: logging.Logger) -> None:
        self._registry = registry
        self._handler = handler
        self._logger = logger

    async def run(self) -> None:
        tasks: dict[str, asyncio.Task[None]] = {}
        try:
            while True:
                entries = {entry.key: entry for entry in self._registry.connection_entries()}
                for key, entry in entries.items():
                    if key not in tasks:
                        tasks[key] = asyncio.create_task(self._run_entry(entry))
                for key in set(tasks) - set(entries):
                    tasks.pop(key).cancel()
                await asyncio.sleep(1)
        finally:
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    async def _run_entry(self, entry: LinkerEntry) -> None:
        assert entry.host is not None and entry.port is not None and entry.secret is not None
        host = f"[{entry.host}]" if ":" in entry.host else entry.host
        uri = f"ws://{host}:{entry.port}/api/v1/linker"
        while True:
            try:
                async with connect(
                    uri,
                    additional_headers={"X-OpenHDO-Secret": entry.secret},
                    open_timeout=5,
                ) as socket:
                    await self._handler(entry, OutboundLinkerSocket(socket))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log_event(
                    self._logger,
                    logging.WARNING,
                    "linker.connection_failed",
                    {"linker_id": entry.id, "error": type(error).__name__},
                )
            await asyncio.sleep(5)
