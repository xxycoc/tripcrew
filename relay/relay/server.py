import asyncio
from contextlib import asynccontextmanager

from aiohttp import web, WSMsgType

from .events import event


class Hub:
    def __init__(self, mode: str):
        self.mode = mode
        self.clients: set[web.WebSocketResponse] = set()
        self.board = event("board", lines=[])
        self.switch_on = None
        self.lock = asyncio.Lock()

    async def publish(self, item: dict):
        await self.publish_many([item])

    async def publish_many(self, items):
        async with self.lock:
            for item in items:
                if item["type"] == "board":
                    self.board = item
                if item["type"] == "switch_on":
                    if self.switch_on is not None:
                        continue
                    self.switch_on = item
                await asyncio.gather(*(self.send(ws, item) for ws in tuple(self.clients)))

    async def send(self, ws, item):
        try:
            # A stalled game must not prevent the Viewer beating Switch.
            await asyncio.wait_for(ws.send_json(item), timeout=1)
        except (ConnectionError, RuntimeError, TimeoutError):
            self.clients.discard(ws)

    async def websocket(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        async with self.lock:
            await ws.send_json(event("hello", mode=self.mode))
            if self.switch_on:
                await ws.send_json(self.switch_on)
            await ws.send_json(self.board)
            self.clients.add(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.clients.discard(ws)
        return ws

    async def close(self, app):
        await asyncio.gather(*(ws.close(code=1001) for ws in tuple(self.clients)))


def applications(hub, mapper):
    ws_app = web.Application()
    ws_app.router.add_get("/", hub.websocket)
    ws_app.on_shutdown.append(hub.close)
    reel_app = web.Application(client_max_size=64 * 1024)

    async def reel(request):
        try:
            items = mapper.reel(await request.json())
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid reel body") from None
        await hub.publish_many(items)
        return web.Response(status=204)

    reel_app.router.add_post("/reel", reel)

    async def activity(request):
        try:
            items = mapper.activity(await request.json())
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid activity body") from None
        await hub.publish_many(items)
        return web.Response(status=204)

    reel_app.router.add_post("/activity", activity)
    return ws_app, reel_app


@asynccontextmanager
async def servers(hub, mapper, ws_port, reel_port):
    runners = []
    try:
        for app, port in zip(applications(hub, mapper), (ws_port, reel_port)):
            runner = web.AppRunner(app)
            runners.append(runner)
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
        yield
    finally:
        for runner in reversed(runners):
            await runner.cleanup()
