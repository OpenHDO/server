"""Pydantic domain and v1 message models for the server boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator


Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9._-]{1,63}$")]
Source = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Brightness = Annotated[int, Field(ge=0, le=255)]
Channel = Annotated[int, Field(ge=0, le=255)]
IdempotencyKey = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Transport = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9._-]{0,31}$")]
DiscoveryTimeout = Annotated[StrictInt, Field(ge=1, le=60)]
ColorMode = Literal["RGB", "RGBW", "CCT"]
DiscoverySessionStatus = Literal["running", "completed", "failed"]
DiscoveryCompletionStatus = Literal["completed", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BrightnessRange(StrictModel):
    min: Literal[0]
    max: Literal[255]


class RgbChannelRange(StrictModel):
    min: Literal[0]
    max: Literal[255]


class RgbColor(StrictModel):
    r: Channel
    g: Channel
    b: Channel


class LightCapability(StrictModel):
    kind: Literal["light"]
    power: bool
    brightness: BrightnessRange
    color_modes: list[ColorMode] | None = Field(default=None, min_length=1)
    rgb_channel_range: RgbChannelRange | None = None

    @field_validator("color_modes")
    @classmethod
    def reject_duplicate_color_modes(cls, value: list[ColorMode] | None) -> list[ColorMode] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("color_modes must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_rgb_range(self) -> "LightCapability":
        rgb_mode = self.color_modes is not None and bool({"RGB", "RGBW"} & set(self.color_modes))
        if rgb_mode and self.rgb_channel_range is None:
            raise ValueError("rgb_channel_range is required for RGB or RGBW")
        if self.rgb_channel_range is not None and not rgb_mode:
            raise ValueError("rgb_channel_range requires RGB or RGBW")
        return self


class DeviceManifest(StrictModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=128)
    capabilities: list[LightCapability] = Field(min_length=1)


class LinkManifest(StrictModel):
    id: Identifier
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
    name: str = Field(min_length=1, max_length=128)
    transports: list[Transport]
    devices: list[DeviceManifest] | None = None

    @field_validator("transports")
    @classmethod
    def reject_duplicate_transports(cls, value: list[Transport]) -> list[Transport]:
        if len(value) != len(set(value)):
            raise ValueError("transports must not contain duplicates")
        return value


class LightState(StrictModel):
    light_id: Identifier
    power: bool
    brightness: Brightness
    rgb_color: RgbColor
    state_revision: int = Field(ge=0)


class LightView(StrictModel):
    light_id: Identifier
    name: str = Field(min_length=1, max_length=128)
    linker_id: Identifier
    capability: LightCapability
    state: LightState | None = None
    updated_at: datetime | None = None


class LightRecord(LightView):
    pass


class CommandBase(StrictModel):
    light_id: Identifier
    command_id: UUID
    idempotency_key: IdempotencyKey


class PowerCommandPayload(CommandBase):
    power: bool


class BrightnessCommandPayload(CommandBase):
    brightness: Brightness


class RgbColorCommandPayload(CommandBase):
    rgb_color: RgbColor


class LightPatchRequest(StrictModel):
    """Ergonomic API input for one abstract Light command."""

    power: bool | None = None
    brightness: Brightness | None = None
    rgb_color: RgbColor | None = None
    idempotency_key: IdempotencyKey

    @model_validator(mode="after")
    def require_one_change(self) -> "LightPatchRequest":
        if sum(value is not None for value in (self.power, self.brightness, self.rgb_color)) != 1:
            raise ValueError("exactly one of power, brightness, or rgb_color is required")
        return self


class EnvelopeBase(StrictModel):
    v: Literal[1]
    id: UUID
    ts: datetime
    source: Source

    @field_validator("ts")
    @classmethod
    def require_timestamp_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("ts must include a timezone")
        return value.astimezone(timezone.utc)


class PowerCommandEnvelope(EnvelopeBase):
    type: Literal["light.command.power"]
    correlation_id: UUID
    payload: PowerCommandPayload


class BrightnessCommandEnvelope(EnvelopeBase):
    type: Literal["light.command.brightness"]
    correlation_id: UUID
    payload: BrightnessCommandPayload


class RgbColorCommandEnvelope(EnvelopeBase):
    type: Literal["light.command.rgb_color"]
    correlation_id: UUID
    payload: RgbColorCommandPayload


LightCommandEnvelope = Annotated[
    PowerCommandEnvelope | BrightnessCommandEnvelope | RgbColorCommandEnvelope,
    Field(discriminator="type"),
]


class LinkRegisterEnvelope(EnvelopeBase):
    type: Literal["link.register"]
    payload: LinkManifest


class LightStateReportedEnvelope(EnvelopeBase):
    type: Literal["light.state.reported"]
    correlation_id: UUID | None = None
    payload: LightState


CommandResultStatus = Literal["accepted", "applied", "rejected", "failed"]


class CommandResultPayload(StrictModel):
    status: CommandResultStatus
    light_id: Identifier
    command_id: UUID
    idempotency_key: IdempotencyKey
    error: str | None = None
    state: LightState | None = None


class CommandResultEnvelope(EnvelopeBase):
    type: Literal["command.result"]
    correlation_id: UUID
    payload: CommandResultPayload


class DiscoveryStartRequest(StrictModel):
    linker_id: Identifier
    timeout_s: DiscoveryTimeout


class DiscoveryStartPayload(StrictModel):
    session_id: UUID
    timeout_s: DiscoveryTimeout


class DiscoveryCandidatePayload(StrictModel):
    session_id: UUID
    candidate_id: Identifier
    name: str = Field(min_length=1, max_length=128)
    transport: Literal["wifi"]
    capabilities: list[LightCapability] = Field(min_length=1)
    requires_pairing: StrictBool


class DiscoveryCompletedPayload(StrictModel):
    session_id: UUID
    status: DiscoveryCompletionStatus
    error: str | None = Field(max_length=512)


class DiscoveryStartEnvelope(EnvelopeBase):
    type: Literal["discovery.start"]
    correlation_id: UUID
    payload: DiscoveryStartPayload

    @model_validator(mode="after")
    def correlation_targets_request(self) -> "DiscoveryStartEnvelope":
        if self.correlation_id != self.id:
            raise ValueError("discovery.start correlation_id must equal envelope id")
        return self


class DiscoveryCandidateEnvelope(EnvelopeBase):
    type: Literal["discovery.candidate"]
    correlation_id: UUID
    payload: DiscoveryCandidatePayload


class DiscoveryCompletedEnvelope(EnvelopeBase):
    type: Literal["discovery.completed"]
    correlation_id: UUID
    payload: DiscoveryCompletedPayload


DiscoveryEnvelope = Annotated[
    DiscoveryStartEnvelope | DiscoveryCandidateEnvelope | DiscoveryCompletedEnvelope,
    Field(discriminator="type"),
]


DiscoveryLinkerEnvelope = Annotated[
    DiscoveryCandidateEnvelope | DiscoveryCompletedEnvelope,
    Field(discriminator="type"),
]


LinkerEnvelope = Annotated[
    LinkRegisterEnvelope
    | LightStateReportedEnvelope
    | CommandResultEnvelope
    | DiscoveryCandidateEnvelope
    | DiscoveryCompletedEnvelope,
    Field(discriminator="type"),
]


class LightUpdatedEnvelope(EnvelopeBase):
    type: Literal["light.updated"]
    correlation_id: UUID | None = None
    payload: LightView


class HealthResponse(StrictModel):
    api_version: Literal[1] = 1
    status: Literal["ok"] = "ok"
    service: Literal["openhdo-server"] = "openhdo-server"
    runtime: Literal["python"] = "python"
    instance_name: str
    linkers_connected: int = Field(ge=0)


class LightsResponse(StrictModel):
    api_version: Literal[1] = 1
    lights: list[LightView]


class DiscoverySessionResponse(StrictModel):
    session_id: UUID
    linker_id: Identifier
    status: DiscoverySessionStatus
    candidates: list[DiscoveryCandidatePayload]
    error: str | None = None


class ProblemResponse(StrictModel):
    api_version: Literal[1] = 1
    error: str
    detail: str
