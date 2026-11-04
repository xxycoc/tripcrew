import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys

import aiohttp

from .config import Config
from .brief import morning_brief
from .demo import play
from .events import Mapper
from .server import Hub, servers
from .switch import Viewer, ViewerError, post, register


async def run(args):
    config = Config.load(args.config) if args.config.exists() else Config()
    if args.command == "post":
        if not args.config.exists():
            raise ValueError("Post requires a configured relay.local.toml")
        result = await post(config, args.text if args.text is not None else morning_brief(), args.room)
        print(json.dumps(result) if args.json else f"*Posted* Viewer message accepted by Switch (event {result['event_id']}).")
        return
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
    parser.add_argument("--json", action="store_true", help="Machine output for post")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("register").add_argument("--token", help="Registration token (prefer SWITCH_REGISTRATION_TOKEN)")
    sub.add_parser("live")
    sub.add_parser("demo").add_argument("--interval", type=positive, default=1.5)
    posting = sub.add_parser("post", help="Post one Viewer message; omit text for today's morning brief")
    posting.add_argument("text", nargs="?")
    posting.add_argument("--room", help="Switch room ID (defaults to switch.room_id)")
    posting.add_argument("--config", type=Path, default=argparse.SUPPRESS)
    posting.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, KeyError, TypeError, ViewerError, aiohttp.ClientError, TimeoutError) as exc:
        # Exception messages from HTTP libraries can include credential-bearing URLs.
        reason = "HTTP connection failed" if isinstance(exc, (aiohttp.ClientError, TimeoutError)) else str(exc)
        if args.command == "post" and isinstance(exc, (aiohttp.ClientError, TimeoutError)):
            reason = "HTTP connection failed or timed out; delivery unknown, check the room before retrying"
        if args.command == "post" and args.json:
            print(json.dumps({"ok": False, "reason": reason}))
        else:
            print(f"Relay stopped: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
