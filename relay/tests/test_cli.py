import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import aiohttp
import pytest

from relay.config import Config


def free_ports():
    with socket.socket() as first, socket.socket() as second:
        first.bind(("127.0.0.1", 0))
        second.bind(("127.0.0.1", 0))
        return first.getsockname()[1], second.getsockname()[1]


async def test_demo_real_cli_loops_all_events_and_accepts_reel(tmp_path):
    ws_port, reel_port = free_ports()
    config = tmp_path / "demo.local.toml"
    config.write_text(f"[server]\nws_port={ws_port}\nreel_port={reel_port}\n")
    project = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "relay", "--config", str(config), "demo", "--interval", "0.01"]
    process = subprocess.Popen(command, cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        line = await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), 5)
        assert line.startswith(b"demo: ws://127.0.0.1:")
        async with aiohttp.ClientSession() as client:
            async with client.ws_connect(f"http://127.0.0.1:{ws_port}") as ws:
                assert (await ws.receive_json(timeout=2))["mode"] == "demo"
                kinds, steps, states, user_messages = set(), set(), set(), 0
                while user_messages < 4:
                    item = await ws.receive_json(timeout=2)
                    kinds.add(item["type"])
                    if item["type"] == "reel":
                        steps.add(item["step"])
                    if item["type"] == "task":
                        states.add(item["state"])
                    if item["type"] == "user_message":
                        user_messages += 1
                assert kinds == {"switch_on", "board", "join", "user_message", "addressed", "agent_message", "task", "reel"}
                assert steps == {"fetch_start", "watching", "identified", "failed"}
                assert states == {"delegated", "accepted", "finalised"}
                payload = {"type": "reel", "step": "identified", "platform": "tiktok", "place": "CLI intake check"}
                async with client.post(f"http://127.0.0.1:{reel_port}/reel", json=payload) as response:
                    assert response.status == 204
                while True:
                    item = await ws.receive_json(timeout=2)
                    if item.get("place") == "CLI intake check":
                        break
                async with client.ws_connect(f"http://127.0.0.1:{ws_port}") as late:
                    assert (await late.receive_json(timeout=2))["mode"] == "demo"
                    assert (await late.receive_json(timeout=2))["type"] == "switch_on"
                    assert (await late.receive_json(timeout=2))["type"] == "board"
    finally:
        process.terminate()
        await asyncio.to_thread(process.wait, 5)
        process.stdout.close()
        process.stderr.close()


def test_live_missing_config_fails_without_demo(tmp_path):
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "relay", "--config", str(tmp_path / "missing.toml"), "live"],
                            cwd=project, capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    assert "requires a configured" in result.stderr
    assert not result.stdout


def test_config_paths_validation_and_credential_binding(tmp_path):
    path = tmp_path / "relay.local.toml"
    path.write_text('[switch]\nbase_url="https://bridge.example.invalid/"\napi_key_path=".local/viewer.json"\n')
    config = Config.load(path)
    assert config.base_url == "https://bridge.example.invalid"
    assert config.api_key_path == tmp_path / ".local" / "viewer.json"
    config.api_key_path.parent.mkdir()
    config.api_key_path.write_text(json.dumps({"agent_id": "test", "api_key": "fake", "base_url": "https://other.invalid", "agent_name": config.agent_name}))
    with pytest.raises(ValueError, match="another bridge"):
        config.credentials()
    for text in ['[server]\nws_port=8771\n', '[actors]\nunknown="invented"\n',
                 '[switch]\nbase_url="https://user:secret@example.invalid"\n']:
        path.write_text(text)
        with pytest.raises(ValueError):
            Config.load(path)
