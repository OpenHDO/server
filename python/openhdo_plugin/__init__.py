"""HDO plugin SDK v1. Plugins are trusted application code, not sandboxed code."""
from .manifest import validate_manifest, PluginError, API_VERSION
from .archive import pack, unpack, MAX_PACKAGE_BYTES
from .context import PluginContext, Provider
from .types import DeviceControl, DeviceSnapshot

__all__ = ["PluginContext", "Provider", "DeviceControl", "DeviceSnapshot", "PluginError", "validate_manifest", "pack", "unpack", "API_VERSION"]

from .errors import ProviderError
