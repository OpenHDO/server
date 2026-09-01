"""Versioned OpenHDO protocol primitives.

The SDK intentionally has no runtime dependencies. Transport, device drivers,
and reconnect policy belong to the application that embeds this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping
from uuid import UUID, uuid4

PROTOCOL_VERSION = 1
_TYPE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")


class ProtocolError(ValueError):
    """Raised when an incoming or outgoing envelope is invalid."""


def _parse_uuid(value: Any, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise ProtocolError(f"{field_name} must be a UUID") from error


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ProtocolError("ts must be an ISO-8601 string")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProtocolError("ts must be an ISO-8601 string") from error
    if timestamp.tzinfo is None:
        raise ProtocolError("ts must include a timezone")
    return timestamp.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class Envelope:
    """A validated, serializable message shared by OpenHDO processes."""

    type: str
    source: str
    payload: Mapping[str, Any]
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: UUID | None = None
    version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol version: {self.version}")
        if not isinstance(self.id, UUID):
            raise ProtocolError("id must be a UUID")
        if self.correlation_id is not None and not isinstance(self.correlation_id, UUID):
            raise ProtocolError("correlation_id must be a UUID")
        if not isinstance(self.type, str) or not _TYPE.fullmatch(self.type):
            raise ProtocolError("type must be a lowercase domain name")
        if not isinstance(self.source, str) or not self.source or len(self.source) > 128:
            raise ProtocolError("source must contain 1 to 128 characters")
        if not isinstance(self.payload, Mapping):
            raise ProtocolError("payload must be an object")
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None:
            raise ProtocolError("timestamp must include a timezone")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "v": self.version,
            "id": str(self.id),
            "type": self.type,
            "ts": self.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": self.source,
            "payload": dict(self.payload),
        }
        if self.correlation_id is not None:
            data["correlation_id"] = str(self.correlation_id)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Envelope":
        if not isinstance(data, Mapping):
            raise ProtocolError("envelope must be an object")
        if data.get("v") != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol version: {data.get('v')}")
        payload = data.get("payload")
        if not isinstance(payload, Mapping):
            raise ProtocolError("payload must be an object")
        correlation = data.get("correlation_id")
        type_value = data.get("type", "")
        source_value = data.get("source", "")
        if not isinstance(type_value, str) or not isinstance(source_value, str):
            raise ProtocolError("type and source must be strings")
        return cls(
            type=type_value,
            source=source_value,
            payload=payload,
            id=_parse_uuid(data.get("id"), "id"),
            timestamp=_parse_timestamp(data.get("ts")),
            correlation_id=None if correlation is None else _parse_uuid(correlation, "correlation_id"),
        )

    @classmethod
    def from_json(cls, value: str | bytes) -> "Envelope":
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError) as error:
            raise ProtocolError("envelope must contain valid JSON") from error
        if not isinstance(data, Mapping):
            raise ProtocolError("envelope must be an object")
        return cls.from_dict(data)
