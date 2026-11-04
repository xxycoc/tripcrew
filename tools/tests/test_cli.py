import json
import base64
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tripcrew.cli import main
from tripcrew.store import ROOT, Store


def place(call, name="Ramen", city="Osaka", category="food"):
    return call("wishlist", "add", "--name", name, "--area", "Station", "--city", city,
                "--category", category, "--price-jpy", "1500", "--hours", "10:00-20:00",
                "--url", "https://example.test/place", "--verified", "--note", "Check opening day")["item"]["id"]


def test_itinerary_lifecycle_and_wishlist_filters(call, demo_trip):
    first, second = place(call), place(call, "Temple", "Kyoto", "attraction")
    call("trip", "day", "1", "add", first)
    call("trip", "day", "1", "add", second, "--position", "1")
    assert call("trip", "show")["trip"]["days"]["1"] == [second, first]
    call("trip", "day", "1", "move", first, "--position", "1")
    assert call("trip", "show")["trip"]["days"]["1"] == [first, second]
    call("trip", "day", "1", "move", second, "--to-day", "2")
    assert call("trip", "show")["trip"]["days"]["2"] == [second]
    assert call("wishlist", "list", "--unplanned")["wishlist"] == []
    filtered = call("wishlist", "list", "--city", "kyoto", "--category", "attraction")["wishlist"]
    assert [item["id"] for item in filtered] == [second]
    assert filtered[0]["verified"] is True
    call("wishlist", "remove", second, ok=False)
    call("trip", "day", "2", "remove", second)
    assert [item["id"] for item in call("wishlist", "list", "--unplanned")["wishlist"]] == [second]
    call("wishlist", "remove", second)
    assert len(call("wishlist", "list")["wishlist"]) == 1


def test_invalid_moves_leave_state_unchanged(call, demo_trip):
    stop = place(call)
    call("trip", "day", "1", "add", stop)
    before = Store().read("trip")
    for args in [("trip", "day", "1", "move", stop, "--position", "0"),
                 ("trip", "day", "1", "move", stop, "--to-day", "0"),
                 ("trip", "day", "8", "add", stop),
                 ("trip", "day", "1", "add", stop),
                 ("trip", "day", "1", "add", "unknown")]:
        call(*args, ok=False)
        assert Store().read("trip") == before


def test_trip_set_preserves_stops_and_validates_dates(call, demo_trip):
    stop = place(call)
    call("trip", "day", "7", "add", stop)
    call("trip", "set", "--cities", "Osaka", "Kyoto", "--interests", "food", "culture", "--budget-sgd", "6500")
    changed = call("trip", "show")["trip"]
    assert changed["days"]["7"] == [stop]
    assert changed["budget_sgd"] == "6500.00"
    assert changed["interests"] == ["food", "culture"]
    for args in [("--end", "2026-12-11"), ("--end", "2026-12-01"), ("--start", "nonsense"),
                 ("--budget-sgd", "1.001"), ("--budget-sgd", "-1")]:
        call("trip", "set", *args, ok=False)
        assert Store().read("trip") == changed


def test_dates_cannot_exclude_spending(call, demo_trip):
    call("spend", "add", "100", "SGD", "--note", "hotel", "--day", "7")
    call("trip", "set", "--end", "2026-12-15", ok=False)
    assert call("spend", "list")["spend"][0]["day"] == 7


def test_wishlist_unknown_price_and_unverified(call):
    result = call("wishlist", "add", "--name", "Park", "--area", "North", "--city", "Osaka", "--category", "tip")
    assert result["item"]["price_jpy"] is None
    assert result["item"]["verified"] is False


@pytest.mark.parametrize("args", [("spend", "add", "0", "SGD", "--note", "bad", "--day", "1"),
                                 ("spend", "add", "1.005", "SGD", "--note", "bad", "--day", "1"),
                                 ("spend", "add", "100", "JPY", "--note", "bad", "--day", "0"),
                                 ("budget", "status", "--day", "8"),
                                 ("trip", "set"), ("wishlist", "remove", "unknown"),
                                 ("reel", "failed", "--reason", " "), ("no-such-command",)])
def test_validation_json(call, demo_trip, args):
    call(*args, ok=False)


def test_human_lines_have_telegram_labels_no_tables_or_newline_injection(call, capsys, demo_trip):
    stop = place(call, name="Noodle\nshop")
    call("trip", "day", "1", "add", stop)
    for args in (["trip", "show"], ["wishlist", "list"], ["budget", "status"]):
        assert main(args) == 0
        output = capsys.readouterr().out
        assert all(line.startswith("*") for line in output.splitlines())
        assert "|" not in output
        assert "Noodle\nshop" not in output
    assert main(["trip", "show"]) == 0
    assert "1500" not in capsys.readouterr().out


def test_real_module_entry_point(tmp_path, demo_trip):
    result = subprocess.run([sys.executable, "-m", "tripcrew", "trip", "show", "--json"],
                            cwd=ROOT / "tools", capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["trip"]["cities"] == ["Osaka", "Kyoto"]


def test_launcher_from_unrelated_directory(tmp_path):
    launcher = ROOT / "bin" / ("tripcrew.cmd" if os.name == "nt" else "tripcrew")
    command = [str(launcher), "trip", "show", "--json"]
    if os.name == "nt":
        command = ["cmd", "/d", "/c", *command]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
    assert json.loads(result.stdout)["trip"] == {
        "start": None, "end": None, "cities": [], "budget_sgd": None, "interests": [], "days": {}}


def test_budget_updates_price_and_source_without_changing_place_or_plan(call, demo_trip):
    stop = place(call)
    call("trip", "day", "1", "add", stop)
    before = Store().read("wishlist")[0]
    itinerary = Store().read("trip")
    for amount, expected in [("2000", "2000"), ("0", "0"), ("unknown", None)]:
        item = call("wishlist", "price", stop, "--price-jpy", amount,
                    "--source-note", "Official menu; lunch set")["item"]
        assert item == {**before, "price_jpy": expected, "price_source_note": "Official menu; lunch set"}
        assert call("wishlist", "list")["wishlist"] == [item]
        assert Store().read("trip") == itinerary
    for amount in ("-1", "NaN", "nonsense"):
        call("wishlist", "price", stop, "--price-jpy", amount, "--source-note", "Menu", ok=False)
        assert Store().read("wishlist") == [item]
    for args in [(stop, "--price-jpy", "10"), (stop, "--price-jpy", "10", "--source-note", " "),
                 ("missing", "--price-jpy", "10", "--source-note", "Menu")]:
        call("wishlist", "price", *args, ok=False)
        assert Store().read("wishlist") == [item]


def receipt_image(tmp_path, name="receipt.PNG"):
    image = tmp_path / name
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
    return image


def test_receipt_saved_by_spend_id_and_shown_in_list(call, demo_trip, tmp_path, capsys):
    image = receipt_image(tmp_path)
    original = image.read_bytes()
    item = call("spend", "add", "12", "SGD", "--note", "Shop", "--day", "2", "--receipt", str(image))["item"]
    assert item["receipt"] == f"receipts/{item['id']}.PNG"
    assert (Store().root / item["receipt"]).read_bytes() == original
    assert image.read_bytes() == original
    assert call("spend", "list")["spend"] == [item]
    assert main(["spend", "list"]) == 0
    assert item["receipt"] in capsys.readouterr().out
    second = call("spend", "add", "5", "SGD", "--note", "Shop", "--receipt", str(image))["item"]
    assert second["receipt"] != item["receipt"]
    assert (Store().root / item["receipt"]).read_bytes() == original


@pytest.mark.parametrize("extension,codec,pixels", [("jpg", "mjpeg", "yuvj420p"), ("png", "png", "rgb24"),
                                                  ("webp", "webp", "yuv420p"), ("gif", "gif", "rgb8"),
                                                  ("bmp", "bmp", "bgr24"), ("tiff", "tiff", "rgb24")])
def test_supported_receipt_formats_decode_and_save(call, demo_trip, tmp_path, extension, codec, pixels):
    import av

    image = tmp_path / f"receipt.{extension}"
    frame = av.VideoFrame(16, 16, "rgb24")
    for plane in frame.planes:
        plane.update(bytes(plane.buffer_size))
    with av.open(str(image), mode="w", format="gif" if codec == "gif" else "image2pipe") as output:
        stream = output.add_stream(codec, rate=1)
        stream.width, stream.height, stream.pix_fmt = 16, 16, pixels
        for packet in [*stream.encode(frame), *stream.encode()]:
            output.mux(packet)
    item = call("spend", "add", "1", "SGD", "--note", "Shop", "--receipt", str(image))["item"]
    assert (Store().root / item["receipt"]).read_bytes() == image.read_bytes()


@pytest.mark.parametrize("kind", ["text", "renamed", "corrupt", "oversize", "missing", "directory", "mismatch"])
def test_invalid_receipts_do_not_record_or_copy(call, demo_trip, tmp_path, kind):
    from tripcrew.receipts import MAX_BYTES

    path = tmp_path / ("receipt.txt" if kind == "text" else "receipt.png")
    if kind == "directory":
        path.mkdir()
    elif kind == "mismatch":
        path = receipt_image(tmp_path, "receipt.jpg")
    elif kind != "missing":
        content = b"\x89PNG\r\n\x1a\n" if kind in ("corrupt", "oversize") else b"not an image"
        path.write_bytes(content + (b"x" * MAX_BYTES if kind == "oversize" else b""))
    call("spend", "add", "1", "SGD", "--note", "Shop", "--receipt", str(path), ok=False)
    assert Store().read("spend") == []
    assert not (Store().root / "receipts").exists()


@pytest.mark.parametrize("failure", ["day", "amount", "category", "fx", "write", "copy"])
def test_failed_spend_never_keeps_receipt(call, demo_trip, tmp_path, monkeypatch, failure):
    image = receipt_image(tmp_path)
    args = ["spend", "add", "1", "SGD", "--note", "Shop", "--receipt", str(image)]
    if failure == "day":
        args += ["--day", "8"]
    elif failure == "amount":
        args[2] = "0"
    elif failure == "category":
        args += ["--category", "unknown"]
    elif failure == "fx":
        args[3] = "JPY"

        def offline(*a, **k):
            raise OSError("offline")

        monkeypatch.setattr("tripcrew.money.urlopen", offline)
    elif failure == "write":
        original = Store.write

        def fail(store, name, value):
            if name == "spend":
                raise OSError("write failed")
            return original(store, name, value)

        monkeypatch.setattr(Store, "write", fail)
    else:
        def fail(*a, **k):
            raise OSError("copy failed")

        monkeypatch.setattr("tripcrew.receipts.os.fsync", fail)
    call(*args, ok=False)
    assert Store().read("spend") == []
    assert not list((Store().root / "receipts").glob("*"))
    assert image.exists()


def test_planner_only_adds_read_only_budget_check_permission():
    settings = json.loads((ROOT / "agents/planner/.claude/settings.json").read_text(encoding="utf-8"))
    allow = settings["permissions"]["allow"]
    for launcher in ("Bash(../../bin/tripcrew", r"PowerShell(..\..\bin\tripcrew.cmd"):
        assert f"{launcher} budget check *)" in allow
    assert all("spend" not in rule and "wishlist price" not in rule for rule in allow)
    assert [rule for rule in allow if " budget " in rule] == [
        "Bash(../../bin/tripcrew budget check *)", r"PowerShell(..\..\bin\tripcrew.cmd budget check *)"]


def test_budget_config_grants_receipt_storage_without_whole_repo_writes():
    import tomllib

    path = ROOT / "agents/budget/.codex/config.toml"
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    assert config["sandbox_mode"] == "workspace-write"
    roots = [(path.parent / root).resolve() for root in config["sandbox_workspace_write"]["writable_roots"]]
    assert roots == [ROOT / "state"]


def test_new_budget_workflow_through_real_launcher(call, demo_trip, tmp_path):
    from tripcrew import money

    launcher = ROOT / "bin" / ("tripcrew.cmd" if os.name == "nt" else "tripcrew")

    def run(agent, *args):
        command = [str(launcher), *args, "--json"]
        if os.name == "nt":
            command = ["cmd", "/d", "/c", *command]
        result = subprocess.run(command, cwd=ROOT / "agents" / agent, capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        data = json.loads(result.stdout)
        assert data["ok"] is True
        return data

    store = Store()
    store.write("fx", {"base": "JPY", "quote": "SGD", "rate": "0.01", "date": "2026-11-04",
                       "fetched_at": money.timestamp().isoformat()})
    call("trip", "set", "--budget-sgd", "1500", "--categories", "flight=700", "other=800")
    pricey, cheap = place(call, "Dinner"), place(call, "Nearby dinner")
    run("budget", "wishlist", "price", pricey, "--price-jpy", "20000", "--source-note", "Official menu")
    run("budget", "wishlist", "price", cheap, "--price-jpy", "1000", "--source-note", "Official menu")
    run("planner", "trip", "day", "1", "add", pricey)
    assert run("planner", "budget", "check", "--day", "1")["days"][0]["status"] == "over"
    image = receipt_image(tmp_path)
    item = run("budget", "spend", "add", "1200", "JPY", "--note", "Shop", "--receipt", str(image),
               "--day", "1", "--category", "other")["item"]
    assert item["amount_sgd"] == "12.00"
    assert (store.root / item["receipt"]).read_bytes() == image.read_bytes()
    run("planner", "trip", "day", "1", "remove", pricey)
    run("planner", "trip", "day", "1", "add", cheap)
    day = run("planner", "budget", "check", "--day", "1")["days"][0]
    assert day["status"] == "under" and day["total_sgd"] == "22.00"
    assert day["difference_sgd"] == "-92.29"
