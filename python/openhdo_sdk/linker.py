"""Helpers for a small Python-based OpenHDO Linker."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .protocol import Envelope, ProtocolError

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True, slots=True)
class LinkerManifest:
    """The stable identity a Linker presents during registration."""

    id: str
    version: str
    name: str
    transports: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _IDENTIFIER.fullmatch(self.id):
            raise ProtocolError("id must be a lowercase Linker identifier")
        if not isinstance(self.version, str) or not _SEMVER.fullmatch(self.version):
            raise ProtocolError("version must use semantic versioning")
        if not isinstance(self.name, str) or not self.name or len(self.name) > 128:
            raise ProtocolError("name must contain 1 to 128 characters")
        if not isinstance(self.transports, tuple):
            raise ProtocolError("transports must be a tuple")
        if any(not isinstance(transport, str) or not _IDENTIFIER.fullmatch(transport) for transport in self.transports):
            raise ProtocolError("transports must be lowercase identifiers")
        if len(set(self.transports)) != len(self.transports):
            raise ProtocolError("transports must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "transports": list(self.transports),
        }

    def registration(self, source: str) -> Envelope:
        return Envelope("link.register", source, self.to_dict())
