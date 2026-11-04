import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
import logging
import math
from uuid import uuid4
from urllib.parse import quote

import aiohttp

from .events import event

log = logging.getLogger(__name__)


class Reopen(Exception):
    pass


class ViewerError(Exception):
    pass


async def post(config, text: str, room_id: str | None = None):
    room = config.room_id if room_id is None else room_id
    if not isinstance(room, str) or not room.strip():
        raise ValueError("Room not set; pass --room or set switch.room_id in relay.local.toml")
    if not text.strip():
        raise ValueError("Message text must not be empty")
    agent_id, key = config.credentials()
    route = config.base_url + "/agents/" + quote(agent_id, safe="") + "/message"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(route, json={"room_id": room, "content": text},
                                headers={"Authorization": f"Bearer {key}"},
                                allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError(f"Switch post failed: HTTP {response.status}; check bridge, key and room membership")
            # Do not echo server bodies: errors may include credentials or message text.
            try:
                result = await response.json()
            except (ValueError, aiohttp.ContentTypeError) as from_error:
                raise ValueError("Switch post returned an invalid receipt; delivery unknown, check the room before retrying") from from_error
    if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("event_id"), str) or not result["event_id"]:
        raise ValueError("Switch post returned an invalid receipt; delivery unknown, check the room before retrying")
    return {"ok": True, "room_id": room, "event_id": result["event_id"]}


@dataclass
class Frame:
    kind: str
    data: dict
    cursor: int | None = None


async def frames(response):
    kind, data, cursor = "message", [], None
    async for raw in response.content:
        line = raw.decode("utf-8-sig").rstrip("\r\n")
        if not line:
            if data:
                value = json.loads("\n".join(data))
                if not isinstance(value, dict):
                    raise ViewerError("Switch SSE data must be an object")
                yield Frame(kind, value, cursor)
            kind, data, cursor = "message", [], None
        elif not line.startswith(":"):
            key, _, value = line.partition(":")
            value = value.removeprefix(" ")
            if key == "event":
                kind = value
            elif key == "data":
                data.append(value)
            elif key == "id":
                cursor = int(value)


async def register(config, token: str):
    if not token:
        raise ValueError("Set SWITCH_REGISTRATION_TOKEN or pass --token")
    path = config.api_key_path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reserve before the one-time API call, so an existing key is never lost.
    output = path.open("x", encoding="utf-8")
    try:
        with output:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.get(config.base_url + "/health", allow_redirects=False) as response:
                    if response.status != 200:
                        raise ViewerError(f"Bridge /health returned HTTP {response.status}; check base_url")
                body = {
                    "name": config.agent_name,
                    "description": "Silent TripCrew game Viewer; never speaks or invokes operations",
                    "connector_type": "custom",
                    "integration_profile": {
                        "connection_model": "always_on", "message_exchange": False,
                        "pre_invocation_mediation": [], "post_invocation_mediation": [],
                        "event_reporting": [],
                    },
                    "overwrite": False,
                }
                async with session.post(config.base_url + "/agents", json=body,
                                        headers={"Authorization": f"Bearer {token}"},
                                        allow_redirects=False) as response:
                    if response.status not in {200, 201}:
                        raise ViewerError(f"Registration returned HTTP {response.status}; 409 means the name already exists")
                    result = await response.json()
                if not isinstance(result.get("id"), str) or not result["id"] or not isinstance(result.get("api_key"), str) or not result["api_key"]:
                    raise ViewerError("Registration response omitted agent ID or API key")
                json.dump({"agent_id": result["id"], "api_key": result["api_key"],
                           "base_url": config.base_url, "agent_name": config.agent_name}, output)
                output.flush()
                return result["id"]
    except BaseException:
        # Close the reservation before unlinking it on Windows.
        # Keep any written response if a later flush failed.
        if path.stat().st_size == 0:
            path.unlink(missing_ok=True)
        raise


class Viewer:
    def __init__(self, config, hub, mapper, *, retry_initial=0.5, retry_max=30):
        self.config, self.hub, self.mapper = config, hub, mapper
        self.agent_id, self.key = config.credentials()
        self.connection_id = str(uuid4())
        self.cursor = None
        self.generation = None
        self.retry_initial, self.retry_max = retry_initial, retry_max
        self.ready = asyncio.Event()
        self.interval = 2.0
        self.healthy = False

    @property
    def route(self):
        return self.config.base_url + "/agents/" + quote(self.agent_id, safe="")

    async def run(self):
        timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=25)
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "text/event-stream"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            delay = self.retry_initial
            while True:
                self.ready.clear()
                self.healthy = False
                try:
                    await self.connect(session)
                except Reopen:
                    continue
                except ViewerError:
                    raise
                except (aiohttp.ClientError, TimeoutError, ValueError):
                    if self.healthy:
                        delay = self.retry_initial
                    log.warning("Switch stream interrupted; retrying in %.1fs", delay)
                else:
                    if self.healthy:
                        delay = self.retry_initial
                    log.warning("Switch stream ended; retrying in %.1fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.retry_max)

    async def connect(self, session):
        params = {"connection_id": self.connection_id, "scope": "all", "filter": "all",
                  "start_from": "head", "client": "tripcrew-viewer", "client_version": "0.1.0"}
        # No protocol declaration opts into the server's documented legacy SSE
        # compatibility, including scalar resume tickets on newer servers.
        headers = {"Last-Event-ID": str(self.cursor)} if self.cursor is not None else {}
        async with session.get(self.route + "/events", params=params, headers=headers,
                               allow_redirects=False) as response:
            if response.status != 200:
                if response.status < 500 and response.status not in {408, 429}:
                    raise ViewerError(f"Switch stream refused: HTTP {response.status}")
                response.raise_for_status()
            if response.content_type != "text/event-stream":
                raise ViewerError("Switch did not return an SSE stream; check bridge URL")
            reader = asyncio.create_task(self.read(response))
            beats = asyncio.create_task(self.heartbeat(session))
            try:
                done, _ = await asyncio.wait((reader, beats), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                reader.cancel()
                beats.cancel()
                await asyncio.gather(reader, beats, return_exceptions=True)

    async def read(self, response):
        async for frame in frames(response):
            if frame.kind == "connection_state":
                self.cursor = frame.data.get("cursor", self.cursor)
                self.generation = frame.data.get("generation")
                interval = frame.data.get("heartbeat_interval_seconds", 2)
                if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
                    raise ViewerError("Invalid Switch heartbeat interval")
                self.interval = interval
                self.ready.set()
                await self.hub.publish(event("switch_on"))
            elif frame.kind == "gap":
                self.cursor = frame.data["resumed_at"]
                log.warning("Switch reported an event gap; continuing at the server cursor")
            elif frame.kind == "evicted":
                if frame.data.get("code") == "taken_over":
                    raise ViewerError("Viewer connection was taken over; stopping to avoid an eviction loop")
                raise Reopen()
            elif frame.cursor is not None:
                if self.cursor is not None and frame.cursor <= self.cursor:
                    continue
                await self.hub.publish_many(self.mapper.map({**frame.data, "type": frame.kind}))
                self.cursor = frame.cursor

    async def heartbeat(self, session):
        await self.ready.wait()
        while True:
            await asyncio.sleep(self.interval)
            body = {"connection_id": self.connection_id, "cursor": self.cursor}
            if self.generation is not None:
                body["generation"] = self.generation
            async with session.post(self.route + "/connection/beat", json=body,
                                    timeout=aiohttp.ClientTimeout(total=2), allow_redirects=False) as response:
                if response.status in {404, 409}:
                    if response.status == 409:
                        with suppress(ValueError, aiohttp.ContentTypeError):
                            data = await response.json()
                            if isinstance(data.get("detail"), dict) and data["detail"].get("code") == "taken_over":
                                raise ViewerError("Viewer connection was taken over")
                    raise Reopen()
                if response.status in {401, 403}:
                    raise ViewerError(f"Switch heartbeat refused: HTTP {response.status}")
                if response.status != 200:
                    raise aiohttp.ClientError("Heartbeat failed")
                self.healthy = True
