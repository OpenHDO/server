"""Standalone Linker WebSocket service for a real local Tuya driver."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_LOGGER = logging.getLogger("openhdo.linker")


class LinkerConfigError(ValueError):
    """Raised when a Linker config cannot be used safely."""


@dataclass(frozen=True, slots=True)
class LinkerServiceConfig:
    host: str
    port: int
    secret: str
    linker_id: str
    linker_version: str
    linker_name: str
    discovery_enabled: bool
    discovery_timeout_s: float
    tuya: Mapping[str, Any] | None = None


def load_config(path: Path) -> LinkerServiceConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise LinkerConfigError(f"config file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise LinkerConfigError(f"invalid JSON config: {error}") from error
    if not isinstance(raw, Mapping):
        raise LinkerConfigError("config root must be an object")

    listen = _section(raw, "listen")
    linker = _section(raw, "linker")
    discovery = _section(raw, "discovery")
    host = _string(listen, "host", default="0.0.0.0")
    port = _integer(listen, "port", default=8765)
    if not 1 <= port <= 65535:
        raise LinkerConfigError("listen.port must be between 1 and 65535")
    secret_value = listen.get("secret", listen.get("minisecret"))
    if not isinstance(secret_value, str):
        raise LinkerConfigError("listen.secret must be a string")
    secret = secret_value
    if not secret:
        raise LinkerConfigError("listen.secret must not be empty")

    linker_id = _string(linker, "id", default="openhdo.linker.rgb-bulb")
    linker_version = _string(linker, "version", default="0.3.0")
    linker_name = _string(linker, "name", default="linker-1")
    if not _IDENTIFIER.fullmatch(linker_id):
        raise LinkerConfigError("linker.id must be a lowercase OpenHDO identifier")
    if not _SEMVER.fullmatch(linker_version):
        raise LinkerConfigError("linker.version must use semantic versioning")
    if not linker_name or len(linker_name) > 128:
        raise LinkerConfigError("linker.name must contain 1 to 128 characters")

    discovery_enabled = _boolean(discovery, "enabled", default=True)
    discovery_timeout_s = _number(discovery, "timeout_s", default=5.0)
    if not 1 <= discovery_timeout_s <= 60:
        raise LinkerConfigError("discovery.timeout_s must be between 1 and 60")
    tuya = raw.get("tuya")
    if tuya is not None and not isinstance(tuya, Mapping):
        raise LinkerConfigError("tuya must be an object")
    return LinkerServiceConfig(
        host=host,
        port=port,
        secret=secret,
        linker_id=linker_id,
        linker_version=linker_version,
        linker_name=linker_name,
        discovery_enabled=discovery_enabled,
        discovery_timeout_s=discovery_timeout_s,
        tuya=tuya,
    )


def _section(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, Mapping):
        raise LinkerConfigError(f"{name} must be an object")
    return value


def _string(raw: Mapping[str, Any], name: str, *, default: str | None = None) -> str:
    value = raw.get(name, default)
    if not isinstance(value, str):
        raise LinkerConfigError(f"{name} must be a string")
    return value


def _integer(raw: Mapping[str, Any], name: str, *, default: int | None = None) -> int:
    value = raw.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LinkerConfigError(f"{name} must be an integer")
    return value


def _number(raw: Mapping[str, Any], name: str, *, default: float | None = None) -> float:
    value = raw.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LinkerConfigError(f"{name} must be a number")
    return float(value)


def _boolean(raw: Mapping[str, Any], name: str, *, default: bool) -> bool:
    value = raw.get(name, default)
    if type(value) is not bool:
        raise LinkerConfigError(f"{name} must be boolean")
    return value


def _external_runtime(config: LinkerServiceConfig):
    try:
        from openhdo_linker import (
            Credentials,
            DeviceDescriptor,
            DiscoveryConfig,
            LinkerBoundary,
            LinkerConfig,
            TuyaDeviceConfig,
            TuyaDpMapping,
            TuyaDiscoveryOptions,
            TuyaLocalDriver,
        )
    except ModuleNotFoundError as error:
        raise LinkerConfigError(
            "openhdo-linker is required; install the OpenHDO Linker package before running linkerct"
        ) from error

    device = None
    light_id = None
    descriptor = None
    if config.tuya is not None:
        raw = config.tuya
        mapping = TuyaDpMapping(
            power=_integer(raw, "dp_power"),
            brightness=_integer(raw, "dp_brightness"),
            color=_integer(raw, "dp_color"),
            color_format=_string(raw, "color_format"),
            brightness_min=_integer(raw, "brightness_min"),
            brightness_max=_integer(raw, "brightness_max"),
            white=_optional_integer(raw, "dp_white"),
            white_min=_optional_integer(raw, "white_min"),
            white_max=_optional_integer(raw, "white_max"),
        )
        device_id = _string(raw, "device_id")
        light_id = _string(raw, "light_id", default=_light_id(device_id))
        if not _IDENTIFIER.fullmatch(light_id):
            raise LinkerConfigError("tuya.light_id must be a lowercase OpenHDO identifier")
        device = TuyaDeviceConfig(
            ip=_string(raw, "ip"),
            device_id=device_id,
            local_key=_string(raw, "local_key"),
            protocol_version=_string(raw, "protocol"),
            dps=mapping,
            public_name=_string(raw, "name", default="LED lamp"),
            port=_integer(raw, "port", default=6668),
            timeout_s=_number(raw, "timeout_s", default=3.0),
            retries=_integer(raw, "retries", default=1),
        )
        modes = ("RGBW",) if mapping.white is not None else ("RGB",)
        descriptor = DeviceDescriptor(light_id, device.public_name, modes)

    linker = LinkerConfig(
        id=config.linker_id,
        version=config.linker_version,
        name=config.linker_name,
        transport="wifi",
        discovery=DiscoveryConfig(timeout_s=config.discovery_timeout_s),
    )
    driver = TuyaLocalDriver(
        device=device,
        discovery=TuyaDiscoveryOptions(enabled=config.discovery_enabled),
    )
    boundary = LinkerBoundary(
        linker,
        Credentials(),
        driver,
        light_id=light_id,
        device_id=device.device_id if device is not None else None,
        descriptor=descriptor,
    )
    return boundary, driver


def _optional_integer(raw: Mapping[str, Any], name: str) -> int | None:
    value = raw.get(name)
    if value is None:
        return None
    return _integer(raw, name)


def _light_id(device_id: str) -> str:
    return f"light.{hashlib.sha256(device_id.encode('utf-8')).hexdigest()[:32]}"


async def run_service(config: LinkerServiceConfig, stop: asyncio.Event | None = None) -> None:
    boundary, driver = _external_runtime(config)
    stop = stop or asyncio.Event()
    async with serve(_handle_client_factory(config, boundary, driver), config.host, config.port, max_size=1024 * 1024):
        _LOGGER.info("Linker listening on %s:%s", config.host, config.port)
        await stop.wait()


def _handle_client_factory(config: LinkerServiceConfig, boundary, driver):
    from openhdo_linker import Envelope, ProtocolError

    async def handle_client(websocket) -> None:
        request = websocket.request
        if request.path != "/api/v1/linker":
            await websocket.close(code=1008, reason="unsupported Linker path")
            return
        provided = request.headers.get("X-OpenHDO-Secret", request.headers.get("X-OpenHDO-Minisecret", ""))
        if not hmac.compare_digest(provided, config.secret):
            await websocket.close(code=1008, reason="invalid Linker secret")
            return

        send_lock = asyncio.Lock()
        driver_lock = asyncio.Lock()
        session_stop = asyncio.Event()
        await _send(websocket, send_lock, boundary.register())
        state_task = (
            asyncio.create_task(_publish_states(websocket, send_lock, driver_lock, boundary, driver, session_stop))
            if boundary.control_enabled
            else None
        )
        try:
            async for raw in websocket:
                try:
                    message = Envelope.from_json(raw)
                except (ProtocolError, ValueError, TypeError) as error:
                    await websocket.close(code=1003, reason=f"invalid v1 envelope: {type(error).__name__}")
                    return
                if message.type not in {"discovery.start", "pairing.start", "light.command.power", "light.command.brightness", "light.command.rgb_color"}:
                    continue
                try:
                    async with driver_lock:
                        if message.type.startswith("light.command.") and boundary.control_enabled:
                            await driver.connect()
                        result = await _handle_linker_message(boundary, message)
                    messages = result if isinstance(result, tuple) else (result,)
                    for response in messages:
                        await _send(websocket, send_lock, response)
                        state = response.payload.get("state")
                        if response.payload.get("status") == "applied" and isinstance(state, Mapping):
                            await _send(
                                websocket,
                                send_lock,
                                Envelope(type="light.state.reported", source=boundary.config.id, payload=state),
                            )
                except Exception:
                    _LOGGER.exception("Linker message handling failed")
        except ConnectionClosed:
            pass
        finally:
            session_stop.set()
            if state_task is not None:
                state_task.cancel()
                await asyncio.gather(state_task, return_exceptions=True)
            async with driver_lock:
                await driver.disconnect()

    return handle_client


async def _handle_linker_message(boundary, message):
    if message.type != "pairing.start":
        return await boundary.handle(message)
    handler = getattr(boundary, "handle_pairing", None)
    if handler is not None:
        return await handler(message)
    from openhdo_linker import Envelope

    return Envelope(
        type="pairing.completed",
        source=boundary.config.id,
        correlation_id=message.id,
        payload={
            "session_id": message.payload["session_id"],
            "candidate_id": message.payload["candidate_id"],
            "status": "failed",
            "error": "pairing is not supported by this Linker",
            "device": None,
        },
    )


async def _publish_states(websocket, send_lock, driver_lock, boundary, driver, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            async with driver_lock:
                await driver.connect()
                state = await driver.poll_state(boundary.device_id)
            await _send(websocket, send_lock, boundary.state(state))
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Tuya state poll failed")
            async with driver_lock:
                await driver.disconnect()
        try:
            await asyncio.wait_for(stop.wait(), timeout=15)
        except TimeoutError:
            pass


async def _send(websocket, send_lock: asyncio.Lock, message) -> None:
    async with send_lock:
        await websocket.send(message.to_json())
