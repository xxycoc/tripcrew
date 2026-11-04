import aiohttp
from aiohttp.test_utils import TestServer

from relay.events import Mapper, event
from relay.server import Hub, applications


async def receive(ws):
    return await ws.receive_json(timeout=2)


async def test_real_websocket_broadcast_reel_and_late_replay(config):
    hub, mapper = Hub("live"), Mapper(config)
    ws_app, reel_app = applications(hub, mapper)
    async with TestServer(ws_app) as ws_server, TestServer(reel_app) as reel_server, aiohttp.ClientSession() as client:
        async with client.ws_connect(ws_server.make_url("/")) as first, client.ws_connect(ws_server.make_url("/")) as second:
            for ws in (first, second):
                assert (await receive(ws))["mode"] == "live"
                assert (await receive(ws))["lines"] == []
            await hub.publish(event("switch_on"))
            for ws in (first, second):
                assert (await receive(ws))["type"] == "switch_on"
            payload = {"type": "reel", "step": "failed", "platform": "instagram", "reason": "Private reel"}
            async with client.post(reel_server.make_url("/reel"), json=payload) as response:
                assert response.status == 204 and await response.read() == b""
            events = []
            for ws in (first, second):
                reel, board = await receive(ws), await receive(ws)
                assert reel["step"] == "failed"
                assert board["lines"] == ["instagram failed: Private reel"]
                events.append((reel, board))
            assert events[0] == events[1]
            await hub.publish(event("switch_on"))
            async with client.ws_connect(ws_server.make_url("/")) as late:
                assert (await receive(late))["type"] == "hello"
                assert (await receive(late))["type"] == "switch_on"
                assert (await receive(late)) == events[0][1]
            async with client.post(reel_server.make_url("/reel"), json={"type": "switch_on"}) as response:
                assert response.status == 400
            async with client.post(reel_server.make_url("/reel"), data="not-json") as response:
                assert response.status == 400
            await hub.publish(event("join", actor="budget"))
            # Invalid reels and duplicate switch_on must not enter the stream.
            assert (await receive(first))["type"] == "join"


async def test_demo_mode_handshake(config):
    hub = Hub("demo")
    app, _ = applications(hub, Mapper(config))
    async with TestServer(app) as server, aiohttp.ClientSession() as client:
        async with client.ws_connect(server.make_url("/")) as ws:
            assert (await receive(ws))["mode"] == "demo"
