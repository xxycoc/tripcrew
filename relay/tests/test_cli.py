import asyncio
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
from datetime import date

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from relay.config import Config
from relay.brief import morning_brief
from test_switch import point_at


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


@pytest.mark.parametrize("today,expected", [
    (date(2026, 12, 10), "trip day 1"), (date(2026, 12, 11), "trip day 2"),
    (date(2026, 12, 16), "trip day 7"), (date(2026, 12, 9), "a test brief"),
    (date(2026, 12, 17), "a test brief"),
])
def test_morning_brief_inclusive_trip_dates(tmp_path, today, expected):
    (tmp_path / "trip.json").write_text(json.dumps({"start": "2026-12-10", "end": "2026-12-16"}))
    text = morning_brief(tmp_path, today)
    assert text == f"@planner @budget Morning brief for {expected} ({today.isoformat()}): please share today's plan and money left, each per your instructions."
    assert "\n" not in text


def test_morning_brief_missing_partial_and_invalid_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPCREW_STATE", str(tmp_path))
    assert "test brief" in morning_brief()
    path = tmp_path / "trip.json"
    for trip in [{}, {"start": None, "end": None}, {"start": "2026-12-10"}]:
        path.write_text(json.dumps(trip))
        assert "test brief" in morning_brief()
    for trip in [[], {"start": "bad", "end": "2026-12-16"}, {"start": "2026-12-17", "end": "2026-12-16"}]:
        path.write_text(json.dumps(trip))
        with pytest.raises(ValueError, match="trip.json"):
            morning_brief()


async def post_cli(tmp_path, *arguments):
    project = Path(__file__).resolve().parents[1]
    process = await asyncio.create_subprocess_exec(sys.executable, "-m", "relay", *arguments,
        cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
    return process.returncode, stdout.decode(), stderr.decode()


@pytest.mark.parametrize("json_first", [False, True])
async def test_post_real_cli_default_brief_and_room_override(tmp_path, config, monkeypatch, json_first):
    monkeypatch.setenv("TRIPCREW_STATE", str(tmp_path))
    today = date.today().isoformat()
    (tmp_path / "trip.json").write_text(json.dumps({"start": today, "end": today}))
    calls = []
    async def receive(request):
        assert request.headers["Authorization"] == "Bearer fake-test-key"
        calls.append(await request.json())
        return web.json_response({"ok": True, "event_id": "cli-event"})
    app = web.Application()
    app.router.add_post("/agents/viewer-id/message", receive)
    async with TestServer(app) as server:
        point_at(config, server)
        path = tmp_path / "relay.local.toml"
        path.write_text(f'[switch]\nbase_url="{config.base_url}"\nroom_id="default-room"\napi_key_path="viewer.json"\n')
        arguments = ["--config", str(path)] + (["--json", "post"] if json_first else ["post", "--json"])
        code, stdout, stderr = await post_cli(tmp_path, *arguments)
        assert code == 0 and not stderr
        assert json.loads(stdout) == {"ok": True, "room_id": "default-room", "event_id": "cli-event"}
        assert calls[0] == {"room_id": "default-room", "content": morning_brief(tmp_path)}
        assert "trip day 1" in calls[0]["content"]
        code, stdout, stderr = await post_cli(tmp_path, "post", "--config", str(path), "--room", "other-room", "@planner @budget custom brief")
        assert code == 0 and "*Posted*" in stdout and not stderr
        assert calls[1] == {"room_id": "other-room", "content": "@planner @budget custom brief"}
        assert "fake-test-key" not in stdout + stderr


@pytest.mark.parametrize("problem", ["config", "room", "key", "http"])
async def test_post_real_cli_errors(tmp_path, config, problem):
    async def receive(request):
        return web.Response(status=503, text="fake-test-key")
    app = web.Application()
    app.router.add_post("/agents/viewer-id/message", receive)
    async with TestServer(app) as server:
        point_at(config, server)
        path = tmp_path / "relay.local.toml"
        if problem != "config":
            path.write_text(f'[switch]\nbase_url="{config.base_url}"\napi_key_path="viewer.json"\n' + ('room_id="room"\n' if problem != "room" else ''))
        if problem == "key":
            config.api_key_path.unlink()
        code, stdout, stderr = await post_cli(tmp_path, "--config", str(path), "post", "brief", "--json")
    expected = {"config": "configured relay.local.toml", "room": "Room not set", "key": "key file is missing", "http": "HTTP 503"}
    assert code == 1 and not stderr
    result = json.loads(stdout)
    assert result["ok"] is False and expected[problem] in result["reason"]
    assert "fake-test-key" not in stdout + stderr


async def test_morning_launchers_from_another_directory_log_and_preserve_exit(tmp_path, config, monkeypatch):
    source = Path(__file__).resolve().parents[2]
    repo = tmp_path / "checkout with spaces"
    (repo / "bin").mkdir(parents=True)
    shutil.copytree(source / "relay" / "relay", repo / "relay" / "relay", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ["morning-brief", "morning-brief.cmd"]:
        shutil.copyfile(source / "bin" / name, repo / "bin" / name)
    venv = repo / "relay" / ".venv"
    if os.name == "nt":
        (venv / "Scripts").mkdir(parents=True)
        shutil.copyfile(sys.executable, venv / "Scripts" / "python.exe")
        shutil.copyfile(Path(sys.prefix) / "pyvenv.cfg", venv / "pyvenv.cfg")
        site = venv / "Lib" / "site-packages"
        site.mkdir(parents=True)
        (site / "dependencies.pth").write_text(str(Path(sys.prefix) / "Lib" / "site-packages"))
    else:
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").symlink_to(sys.executable)
    monkeypatch.setenv("TRIPCREW_STATE", str(tmp_path))
    calls, status = [], 200
    async def receive(request):
        assert request.headers["Authorization"] == "Bearer fake-test-key"
        calls.append(await request.json())
        return web.json_response({"ok": True, "event_id": "launcher-event"}, status=status)
    app = web.Application()
    app.router.add_post("/agents/viewer-id/message", receive)
    async with TestServer(app) as server:
        point_at(config, server)
        shutil.copyfile(config.api_key_path, repo / "relay" / "viewer.json")
        (repo / "relay" / "relay.local.toml").write_text(f'[switch]\nbase_url="{config.base_url}"\nroom_id="launcher-room"\napi_key_path="viewer.json"\n')
        launchers = []
        if os.name == "nt":
            launchers.append([os.environ["COMSPEC"], "/d", "/c", str(repo / "bin" / "morning-brief.cmd")])
        if shutil.which("sh"):
            launchers.append([shutil.which("sh"), str(repo / "bin" / "morning-brief")])
        assert launchers
        for command in launchers:
            for status in [200, 503]:
                process = await asyncio.create_subprocess_exec(*command, cwd=tmp_path,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                stdout, stderr = await asyncio.wait_for(process.communicate(), 10)
                assert process.returncode == (0 if status == 200 else 1), stderr.decode()
                assert not stdout and not stderr
    assert calls == [{"room_id": "launcher-room", "content": morning_brief(tmp_path)}] * (2 * len(launchers))
    log = (repo / "relay" / ".local" / "brief.log").read_text()
    assert log.count("*Posted*") == len(launchers)
    assert log.count("HTTP 503") == len(launchers)
    assert "fake-test-key" not in log


@pytest.mark.skipif(os.name != "nt", reason="Windows Task Scheduler script")
def test_brief_task_install_run_uninstall_with_mock_scheduler(tmp_path):
    repo = tmp_path / "checkout with spaces"
    (repo / "scripts").mkdir(parents=True)
    script = repo / "scripts" / "brief-task.ps1"
    shutil.copyfile(Path(__file__).resolve().parents[2] / "scripts" / "brief-task.ps1", script)
    for file in ["bin/morning-brief.cmd", "relay/.venv/Scripts/python.exe", "relay/relay.local.toml"]:
        path = repo / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    harness = tmp_path / "scheduler-check.ps1"
    harness.write_text(r'''
param($Script)
$ErrorActionPreference = 'Stop'
$global:briefTestExists = $false
function Get-ScheduledTask { param($TaskName, $ErrorAction) if ($global:briefTestExists) { @{TaskName=$TaskName} } }
function New-ScheduledTaskAction { param($Execute, $Argument, $WorkingDirectory) [pscustomobject]$PSBoundParameters }
function New-ScheduledTaskTrigger { param([switch]$Daily, [datetime]$At) @{Daily=[bool]$Daily; At=$At.ToString('HH:mm')} }
function New-ScheduledTaskPrincipal { param($UserId, $LogonType, $RunLevel) [pscustomobject]$PSBoundParameters }
function New-ScheduledTaskSettingsSet {
    param($MultipleInstances, $ExecutionTimeLimit, [switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries)
    @{MultipleInstances=$MultipleInstances; Minutes=$ExecutionTimeLimit.TotalMinutes;
      Battery=[bool]$AllowStartIfOnBatteries; KeepOnBattery=[bool]$DontStopIfGoingOnBatteries}
}
function Register-ScheduledTask {
    param($TaskName, $Action, $Trigger, $Principal, $Settings, $Description)
    $global:briefTestRegistration = [pscustomobject]$PSBoundParameters
    $global:briefTestExists = $true
}
function Start-ScheduledTask { param($TaskName) $global:briefTestStarted = $TaskName }
function Unregister-ScheduledTask { param($TaskName, [switch]$Confirm) $global:briefTestRemoved = $TaskName; $global:briefTestExists = $false }
& $Script install -At 09:15 | Out-Null
try { & $Script install | Out-Null; throw 'duplicate install accepted' }
catch { if ($_.Exception.Message -notlike '*already exists*') { throw } }
& $Script run | Out-Null
& $Script uninstall | Out-Null
& $Script uninstall | Out-Null
try { & $Script run | Out-Null; throw 'missing task accepted' }
catch { if ($_.Exception.Message -notlike '*not installed*') { throw } }
try { & $Script install -At 25:00 | Out-Null; throw 'invalid time accepted' }
catch { if ($_.FullyQualifiedErrorId -notlike 'ParameterArgumentValidationError*') { throw } }
@{Registration=$global:briefTestRegistration; Started=$global:briefTestStarted; Removed=$global:briefTestRemoved} | ConvertTo-Json -Depth 8
''')
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness), str(script)],
        capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    registration = data["Registration"]
    assert registration["TaskName"].startswith("TripCrew-MorningBrief-S-1-")
    assert data["Started"] == data["Removed"] == registration["TaskName"]
    assert registration["Action"]["Execute"].lower().endswith("cmd.exe")
    assert registration["Action"]["Argument"] == f'/d /s /c ""{repo / "bin" / "morning-brief.cmd"}""'
    assert registration["Action"]["WorkingDirectory"] == str(repo)
    assert registration["Trigger"] == {"Daily": True, "At": "09:15"}
    assert registration["Principal"]["LogonType"] == "Interactive"
    assert registration["Principal"]["RunLevel"] == "Limited"
    assert registration["Settings"] == {"MultipleInstances": "IgnoreNew", "Minutes": 2, "Battery": True, "KeepOnBattery": True}
