"""Stable provider boundary; runtime validation remains the host's responsibility."""
from typing import Literal, TypedDict, NotRequired, Any


class DeviceControl(TypedDict):
    code: str
    name: str
    type: Literal["Boolean", "Integer", "Enum", "Json"]
    constraints: dict[str, Any]


class DeviceSnapshot(TypedDict):
    external_id: str
    name: str
    kind: str
    product_name: str
    available: bool
    controls: list[DeviceControl]
    state: dict[str, Any]
    updated_at: str | None
    status_specs: NotRequired[dict[str, dict[str, Any]]]
    state_revision: NotRequired[int]
    state_stale: NotRequired[bool]
    device_type: NotRequired[str]
    icon: NotRequired[str | None]
