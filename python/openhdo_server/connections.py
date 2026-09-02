"""Process-local WebSocket connections and transient event fan-out."""

from __future__ import annotations

import asyncio

from fastapi import WebSocket

from .models import EnvelopeBase, LightUpdatedEnvelope


class LinkerConnections:
    """Track one active control connection per linker identity."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def attach(self, linker_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            previous = self._connections.get(linker_id)
            self._connections[linker_id] = websocket
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=4001, reason="replaced by a newer linker connection")
            except Exception:
                pass

    async def detach(self, linker_id: str, websocket: WebSocket) -> bool:
        async with self._lock:
            if self._connections.get(linker_id) is websocket:
                del self._connections[linker_id]
                return True
            return False

    async def send(self, linker_id: str, message: EnvelopeBase) -> bool:
        async with self._lock:
            websocket = self._connections.get(linker_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(message.model_dump(mode="json"))
            return True
        except Exception:
            await self.detach(linker_id, websocket)
            return False

    async def count(self) -> int:
        async with self._lock:
            return len(self._connections)

    async def is_connected(self, linker_id: str) -> bool:
        async with self._lock:
            return linker_id in self._connections


class LightEventHub:
    """Publish transient canonical updates to connected event clients."""

    def __init__(self, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[LightUpdatedEnvelope]] = set()

    def subscribe(self) -> asyncio.Queue[LightUpdatedEnvelope]:
        queue: asyncio.Queue[LightUpdatedEnvelope] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[LightUpdatedEnvelope]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: LightUpdatedEnvelope) -> None:
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                queue.get_nowait()
                queue.put_nowait(event)
