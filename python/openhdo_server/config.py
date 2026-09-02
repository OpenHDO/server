"""Typed configuration boundary for the OpenHDO server."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class SettingsError(ValueError):
    """Raised when server configuration cannot be loaded safely."""


_DEFAULT_AUTH_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "openhdo-auth.sqlite3"


class ServerSettings(BaseModel):
    """Validated settings with a local-first, least-privilege default."""

    model_config = ConfigDict(extra="ignore")

    config_version: Literal[1] = 1
    instance_name: str = Field(default="openhdo-server", min_length=1, max_length=64)
    host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["trace", "debug", "info", "warn", "error"] = "info"
    api_token: str | None = Field(default=None, min_length=8)
    cors_origins: tuple[str, ...] = ()
    auth_db_path: str = str(_DEFAULT_AUTH_DB_PATH)
    admin_username: str | None = Field(default=None, min_length=1, max_length=64)
    admin_password: str | None = Field(default=None, min_length=8, max_length=256)

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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def normalize_cors_origins(cls, value: object) -> object:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            origins = tuple(origin.strip() for origin in value.split(","))
            if any(not origin for origin in origins):
                raise ValueError("cors_origins must contain comma-separated exact origins")
            return origins
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        origins = tuple(dict.fromkeys(value))
        for origin in origins:
            parsed = urlsplit(origin)
            try:
                parsed.port
            except ValueError as error:
                raise ValueError("cors_origins must contain valid exact origins") from error
            if (
                "*" in origin
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or origin != f"{parsed.scheme}://{parsed.netloc}"
            ):
                raise ValueError("cors_origins must contain valid exact origins")
        return origins

    @model_validator(mode="after")
    def require_bootstrap_pair(self) -> "ServerSettings":
        if (self.admin_username is None) != (self.admin_password is None):
            raise ValueError("admin_username and admin_password must be configured together")
        return self

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
    "OPENHDO_CORS_ORIGINS": "cors_origins",
    "OPENHDO_AUTH_DB": "auth_db_path",
    "OPENHDO_ADMIN_USERNAME": "admin_username",
    "OPENHDO_ADMIN_PASSWORD": "admin_password",
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
