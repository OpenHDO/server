"""OpenHDO's Python server runtime."""

from .config import ServerSettings, load_settings


def create_app(*args, **kwargs):
    """Create an application without importing the process-wide app eagerly."""

    from .app import create_app as create_application

    return create_application(*args, **kwargs)


__all__ = ["ServerSettings", "create_app", "load_settings"]
