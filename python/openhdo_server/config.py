"""Typed configuration boundary for the OpenHDO server."""

from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class SettingsError(ValueError):
    """Raised when server configuration cannot be loaded safely."""


class ServerSettings(BaseModel):
    """Validated settings with a local-first, least-privilege default."""

    model_config = ConfigDict(extra="ignore")

    config_version: Literal[1] = 1
    instance_name: str = Field(default="openhdo-server", min_length=1, max_length=64)
    host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["trace", "debug", "info", "warn", "error"] = "info"
    api_token: str | None = Field(default=None, min_length=8)

    @field_validator("instance_name")
    @classmethod
    def validate_instance_name(cls, value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        if any(character not in allowed for character in value):
            raise ValueError("instance_name contains unsupported characters")
        return value

    @field_validator("api_token", mode="before")
    @classmethod
    def normalize_api_token(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @model_validator(mode="after")
    def require_token_for_non_local_host(self) -> "ServerSettings":
        if self.host not in {"127.0.0.1", "localhost", "::1"} and self.api_token is None:
            raise ValueError("api_token is required when host is not local")
        return self


_ENVIRONMENT_KEYS = {
    "OPENHDO_CONFIG_VERSION": "config_version",
    "OPENHDO_INSTANCE_NAME": "instance_name",
    "OPENHDO_HOST": "host",
    "OPENHDO_PORT": "port",
    "OPENHDO_LOG_LEVEL": "log_level",
    "OPENHDO_API_TOKEN": "api_token",
}


def load_settings(environ: Mapping[str, str] | None = None) -> ServerSettings:
    """Load and validate the supported OPENHDO_* environment settings."""

    values = environ if environ is not None else os.environ
    raw: dict[str, str] = {
        setting_name: values[environment_name]
        for environment_name, setting_name in _ENVIRONMENT_KEYS.items()
        if environment_name in values
    }
    try:
        return ServerSettings.model_validate(raw)
    except ValidationError as error:
        raise SettingsError(str(error)) from error
