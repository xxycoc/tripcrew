import asyncio
from contextlib import suppress
import json

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from relay.events import Mapper
from relay.server import Hub, applications
from relay.switch import Viewer, ViewerError, register
from conftest import domain, message, sse


def point_at(config, server):
    config.base_url = str(server.make_url("")).rstrip("/")
    config.api_key_path.write_text(json.dumps({"agent_id": "viewer-id", "api_key": "fake-test-key",
        "base_url": config.base_url, "agent_name": config.agent_name}))


async def test_fake_sse_to_websocket_reconnect_resume_and_beat(config):
    requests, opens, beats = [], [], []
    beat_received, finished = asyncio.Event(), asyncio.Event()

    async def stream(request):
        requests.append((request.method, request.path))
        assert request.headers["Authorization"] == "Bearer fake-test-key"
        assert request.query["scope"] == request.query["filter"] == "all"
        assert "rooms" not in request.query
        opens.append((dict(request.query), request.headers.get("Last-Event-ID")))
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        count = len(opens)
        state = {"connection_id": request.query["connection_id"], "agent_id": "viewer-id",
                 "scope": "all", "filter": "all", "rooms": ["room-example"],
                 "cursor": 0 if count == 1 else 2, "protocol": 7,
                 "generation": count, "heartbeat_interval_seconds": 0.01,
                 "server": {"version": "test"}, "client": {}}
        await response.write(sse("connection_state", state))
        if count == 1:
            await response.write(b": keepalive\r\n\r\n")
            join = domain("room_join", sequence=1, member="@planner:example.invalid",
                          member_name="custom.planner.owner", timestamp=1804389129000, listening=False)
            await response.write(sse("room_join", join, 1))
            await response.write(sse("message", message(sequence=2), 2))
            await asyncio.wait_for(beat_received.wait(), 2)
        else:
            # Deliberately duplicate a frame to exercise duplicate suppression.
            await response.write(sse("message", message(sequence=2), 2))
            await response.write(sse("message", message(sequence=3, sender="@planner:example.invalid",
                sender_name="custom.planner.owner", body="Found Osaka food\nmore"), 3))
            await asyncio.wait_for(finished.wait(), 2)
        return response

    async def beat(request):
        requests.append((request.method, request.path))
        assert request.headers["Authorization"] == "Bearer fake-test-key"
        beats.append(await request.json())
        beat_received.set()
        return web.json_response({"ok": True, "rooms": ["room-example"], "cursor": 2})

    app = web.Application()
    app.router.add_get("/agents/viewer-id/events", stream)
    app.router.add_post("/agents/viewer-id/connection/beat", beat)
    hub, mapper = Hub("live"), Mapper(config)
    ws_app, _ = applications(hub, mapper)
    async with TestServer(app) as switch, TestServer(ws_app) as game, aiohttp.ClientSession() as client:
        point_at(config, switch)
        viewer = Viewer(config, hub, mapper, retry_initial=0.001)
        async with client.ws_connect(game.make_url("/")) as ws:
            assert (await ws.receive_json())["type"] == "hello"
            assert (await ws.receive_json())["type"] == "board"
            task = asyncio.create_task(viewer.run())
            try:
                received = [await ws.receive_json(timeout=2) for _ in range(8)]
                assert [item["type"] for item in received] == ["switch_on", "join", "user_message", "addressed", "addressed", "board", "agent_message", "board"]
                assert received[-2]["text"] == "Found Osaka food"
                assert viewer.cursor == 3
                assert opens[0][1] is None and opens[1][1] == "2"
                assert opens[0][0]["connection_id"] == opens[1][0]["connection_id"]
                assert beats[0]["cursor"] == 2 and beats[0]["generation"] == 1
                assert {path for _, path in requests} == {"/agents/viewer-id/events", "/agents/viewer-id/connection/beat"}
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                finished.set()


@pytest.mark.parametrize("status", [404, 409])
async def test_dead_heartbeat_reopens_without_backoff(config, status):
    opened, finish = asyncio.Event(), asyncio.Event()
    count = 0

    async def stream(request):
        nonlocal count
        count += 1
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(sse("connection_state", {"cursor": 0, "heartbeat_interval_seconds": 0.005}))
        if count == 2:
            opened.set()
        await finish.wait()
        return response

    async def beat(request):
        return web.json_response({"detail": "no stream"}, status=status)

    app = web.Application()
    app.router.add_get("/agents/viewer-id/events", stream)
    app.router.add_post("/agents/viewer-id/connection/beat", beat)
    async with TestServer(app) as server:
        point_at(config, server)
        viewer = Viewer(config, Hub("live"), Mapper(config), retry_initial=10)
        task = asyncio.create_task(viewer.run())
        try:
            await asyncio.wait_for(opened.wait(), 1)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            finish.set()


async def test_gap_resets_cursor_after_server_restart(config, caplog):
    async def stream(request):
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(sse("connection_state", {"cursor": 100, "heartbeat_interval_seconds": 2}))
        await response.write(sse("gap", {"from_sequence": 100, "resumed_at": 0, "reason": "cursor ahead"}))
        await response.write(sse("message", message(sequence=1), 1))
        return response
    app = web.Application()
    app.router.add_get("/agents/viewer-id/events", stream)
    async with TestServer(app) as server:
        point_at(config, server)
        hub = Hub("live")
        viewer = Viewer(config, hub, Mapper(config))
        async with aiohttp.ClientSession() as client:
            await viewer.connect(client)
        assert viewer.cursor == 1 and len(hub.board["lines"]) == 1
        assert "event gap" in caplog.text


@pytest.mark.parametrize("kind,payload", [
    ("task_delegate", {"summary": "Check food budget", "description": "Osaka"}),
    ("task_accept", {}), ("task_finalise", {"outcome": "Checked"}),
])
async def test_documented_legacy_task_frames(config, kind, payload):
    async def stream(request):
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(sse("connection_state", {"cursor": 0, "heartbeat_interval_seconds": 2}))
        data = domain(kind, task_id="example-task", requester_agent_id="planner-id",
                      performer_agent_id="budget-id", **payload)
        await response.write(sse(kind, data, 1))
        return response
    class Recorder(Hub):
        def __init__(self):
            super().__init__("live")
            self.items = []
        async def publish_many(self, items):
            self.items.extend(items)
            await super().publish_many(items)
    app = web.Application()
    app.router.add_get("/agents/viewer-id/events", stream)
    async with TestServer(app) as server:
        point_at(config, server)
        hub = Recorder()
        viewer = Viewer(config, hub, Mapper(config))
        async with aiohttp.ClientSession() as client:
            await viewer.connect(client)
        assert [item["type"] for item in hub.items] == ["switch_on", "task"]


async def test_takeover_stops_instead_of_fighting_other_client(config):
    async def stream(request):
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(sse("connection_state", {"cursor": 0, "heartbeat_interval_seconds": 2}))
        await response.write(sse("evicted", {"code": "taken_over", "reason": "Superseded"}))
        return response
    app = web.Application()
    app.router.add_get("/agents/viewer-id/events", stream)
    async with TestServer(app) as server:
        point_at(config, server)
        viewer = Viewer(config, Hub("live"), Mapper(config))
        with pytest.raises(ViewerError, match="taken over"):
            await viewer.run()


async def test_http_failure_backs_off_and_auth_is_terminal(config, monkeypatch):
    calls, sleeps = [], []
    viewer = Viewer(config, Hub("live"), Mapper(config), retry_initial=0.5, retry_max=1)
    async def connect(session):
        calls.append(1)
        if len(calls) == 4:
            raise ViewerError("auth refused")
        raise aiohttp.ClientConnectionError("dropped")
    async def sleep(delay):
        sleeps.append(delay)
    monkeypatch.setattr(viewer, "connect", connect)
    monkeypatch.setattr("relay.switch.asyncio.sleep", sleep)
    with pytest.raises(ViewerError):
        await viewer.run()
    assert sleeps == [0.5, 1, 1]


async def test_custom_registration_once_and_failure_cleanup(config):
    config.api_key_path.unlink()
    requests = []
    async def health(request):
        return web.json_response({"ok": True})
    async def create(request):
        body = await request.json()
        assert request.headers["Authorization"] == "Bearer fake-registration-token"
        assert body["connector_type"] == "custom"
        assert body["integration_profile"]["connection_model"] == "always_on"
        assert body["integration_profile"]["message_exchange"] is False
        assert body["overwrite"] is False
        requests.append(body)
        return web.json_response({"id": "viewer-id", "api_key": "fake-new-key"})
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/agents", create)
    async with TestServer(app) as server:
        config.base_url = str(server.make_url("")).rstrip("/")
        assert await register(config, "fake-registration-token") == "viewer-id"
        assert config.credentials() == ("viewer-id", "fake-new-key")
        assert "fake-registration-token" not in config.api_key_path.read_text()
        with pytest.raises(FileExistsError):
            await register(config, "fake-registration-token")
        assert len(requests) == 1

    config.api_key_path.unlink()
    app = web.Application()
    app.router.add_get("/health", health)
    async def conflict(request):
        return web.Response(status=409)
    app.router.add_post("/agents", conflict)
    async with TestServer(app) as server:
        config.base_url = str(server.make_url("")).rstrip("/")
        with pytest.raises(ViewerError, match="409"):
            await register(config, "fake-registration-token")
        assert not config.api_key_path.exists()
