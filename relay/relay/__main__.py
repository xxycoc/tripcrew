import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys

import aiohttp

from .config import Config
from .demo import play
from .events import Mapper
from .server import Hub, servers
from .switch import Viewer, ViewerError, register


async def run(args):
    config = Config.load(args.config) if args.config.exists() else Config()
    if args.command == "register":
        if not args.config.exists():
            raise ValueError("Copy relay.example.toml to relay.local.toml and configure it first")
        agent_id = await register(config, args.token or os.environ.get("SWITCH_REGISTRATION_TOKEN", ""))
        print(f"Registered Viewer {agent_id}; credentials saved locally. Invite it to the room before live mode.")
        return
    if args.command == "live" and not args.config.exists():
        raise ValueError("Live mode requires a configured relay.local.toml")
    hub, mapper = Hub(args.command if args.command == "demo" else "live"), Mapper(config)
    viewer = Viewer(config, hub, mapper) if args.command == "live" else None
    async with servers(hub, mapper, config.ws_port, config.reel_port):
        print(f"{hub.mode}: ws://127.0.0.1:{config.ws_port}, POST http://127.0.0.1:{config.reel_port}/reel", flush=True)
        if viewer:
            await viewer.run()
        else:
            await play(hub, mapper, args.interval)


def positive(value):
    number = float(value)
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("interval must be positive and finite")
    return number


def main():
    parser = argparse.ArgumentParser(description="Silent Switch Viewer and game relay")
    parser.add_argument("--config", type=Path, default=Path("relay.local.toml"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("register").add_argument("--token", help="Registration token (prefer SWITCH_REGISTRATION_TOKEN)")
    sub.add_parser("live")
    sub.add_parser("demo").add_argument("--interval", type=positive, default=1.5)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, KeyError, TypeError, ViewerError, aiohttp.ClientError) as exc:
        # Exception messages from HTTP libraries can include credential-bearing URLs.
        print(f"Relay stopped: {exc}" if not isinstance(exc, aiohttp.ClientError) else "Relay stopped: HTTP connection failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
