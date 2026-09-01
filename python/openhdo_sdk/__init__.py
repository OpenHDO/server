"""Small stdlib-only building block for OpenHDO integrations."""

from .linker import LinkerManifest
from .protocol import Envelope, ProtocolError, PROTOCOL_VERSION

__all__ = ["Envelope", "LinkerManifest", "ProtocolError", "PROTOCOL_VERSION"]
