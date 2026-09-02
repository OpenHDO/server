"""Command line entry point for the standalone OpenHDO Linker service."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .runtime import LinkerConfigError, _external_runtime, load_config, run_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the standalone OpenHDO Linker service.")
    parser.add_argument("--config", type=Path, default=Path("data/linker/config.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="listen for the OpenHDO server")
    subparsers.add_parser("validate", help="validate config and real Linker dependencies")
    subparsers.add_parser("discover", help="run a real local-network Tuya discovery")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == "validate":
            _external_runtime(config)
            print(f"linkerct config ok host={config.host} port={config.port} id={config.linker_id}")
            return
        if args.command == "discover":
            asyncio.run(_discover(config))
            return
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        asyncio.run(run_service(config))
    except (LinkerConfigError, ValueError) as error:
        parser.error(str(error))


async def _discover(config) -> None:
    boundary, driver = _external_runtime(config)
    del boundary
    try:
        from openhdo_linker import Credentials, DiscoveryConfig

        devices = await driver.discover(DiscoveryConfig(timeout_s=config.discovery_timeout_s), Credentials())
        print(json.dumps([device.to_payload() for device in devices], ensure_ascii=False, indent=2))
    finally:
        await driver.disconnect()


if __name__ == "__main__":
    main()
