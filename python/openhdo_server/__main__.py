"""Command-line entry point for the OpenHDO Python server."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from .config import SettingsError, load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OpenHDO Python server runtime.")
    parser.add_argument("--check", action="store_true", help="validate configuration and exit")
    parser.add_argument("--version", action="store_true", help="print runtime and protocol versions")
    args = parser.parse_args()

    try:
        settings = load_settings()
    except SettingsError as error:
        print(f"openhdo-server configuration error: {error}", file=sys.stderr)
        return 2

    if args.version:
        print("openhdo-server 0.1.0 runtime=python api=v1")
        return 0
    if args.check:
        print(f"openhdo-server configuration ok host={settings.host} port={settings.port}")
        return 0

    from .app import create_app

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
