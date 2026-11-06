import json
import base64
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

import pytest

from tripcrew.cli import main
from tripcrew.store import ROOT, Store
from tripcrew.activity import post_event


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


def test_map_itinerary_order_and_read_only(call, capsys, demo_trip):
    first, second, third = place(call, "First"), place(call, "Second"), place(call, "Third")
    for stop in (first, second, third):
        call("trip", "day", "2", "add", stop)
    call("trip", "day", "2", "move", third, "--position", "1")
    before = {p.name: p.read_bytes() for p in Store().root.glob("*.json")}
    route = call("trip", "map", "2")["days"][0]
    assert [stop["id"] for stop in route["stops"]] == [third, first, second]
    assert route["dropped_stops"] == []
    assert urlsplit(route["url"]).path == "/maps/dir/"
    assert parse_qs(urlsplit(route["url"]).query) == {
        "api": ["1"], "origin": ["Third, Station, Osaka"], "destination": ["Second, Station, Osaka"],
        "waypoints": ["First, Station, Osaka"], "travelmode": ["transit"]}
    assert main(["trip", "map", "2"]) == 0
    assert capsys.readouterr().out == f"*Day 2* {route['url']}\n"
    assert {p.name: p.read_bytes() for p in Store().root.glob("*.json")} == before


def test_map_one_stop_search_and_encoding(call, demo_trip):
    item = call("wishlist", "add", "--name", "伏見稲荷, Tea & Food", "--area", "伏見 区",
                "--city", "京都", "--category", "attraction", "--url", "https://maps.app.goo.gl/example")["item"]
    call("trip", "day", "1", "add", item["id"])
    route = call("trip", "map", "1")["days"][0]
    assert route["stops"] == [{key: item[key] for key in ("id", "name", "area", "city")}]
    assert route["url"].startswith("https://www.google.com/maps/search/?api=1&query=")
    assert parse_qs(urlsplit(route["url"]).query) == {
        "api": ["1"], "query": ["伏見稲荷, Tea & Food, 伏見 区, 京都"]}
    assert "%E4%BC%8F" in route["url"] and "%2C" in route["url"] and "%26" in route["url"]
    assert " " not in route["url"] and "maps.app.goo.gl" not in route["url"]


def test_map_directions_encoding_and_two_stops(call, demo_trip):
    first, second, third = place(call, "大阪 城"), place(call, "Tea, & cakes"), place(call, "京都 駅", "Kyoto")
    for stop in (first, second, third):
        call("trip", "day", "1", "add", stop)
    url = call("trip", "map", "1")["days"][0]["url"]
    assert parse_qs(urlsplit(url).query) == {
        "api": ["1"], "origin": ["大阪 城, Station, Osaka"], "destination": ["京都 駅, Station, Kyoto"],
        "waypoints": ["Tea, & cakes, Station, Osaka"], "travelmode": ["transit"]}
    call("trip", "day", "1", "remove", second)
    assert "waypoints" not in parse_qs(urlsplit(call("trip", "map", "1")["days"][0]["url"]).query)


def test_map_empty_day_and_no_planned_days(call, capsys, demo_trip):
    assert call("trip", "map", "2")["days"] == [
        {"day": 2, "url": None, "stops": [], "dropped_stops": [], "message": "Unplanned; no stops to map."}]
    assert main(["trip", "map", "2"]) == 0
    assert capsys.readouterr().out == "*Day 2* Unplanned; no stops to map.\n"
    assert call("trip", "map")["days"] == []
    assert main(["trip", "map"]) == 0
    output = capsys.readouterr().out
    assert "No planned days" in output and "https://" not in output


def test_map_all_planned_days_in_numeric_order(call, capsys, demo_trip):
    call("trip", "set", "--end", "2026-12-20")
    stop = place(call)
    for day in ("10", "2"):
        call("trip", "day", day, "add", stop)
    days = call("trip", "map")["days"]
    assert [day["day"] for day in days] == [2, 10]
    assert main(["trip", "map"]) == 0
    assert capsys.readouterr().out.splitlines() == [f"*Day {day['day']}* {day['url']}" for day in days]


@pytest.mark.parametrize("count", [5, 6, 12])
def test_map_mobile_waypoint_limit(call, capsys, demo_trip, count):
    stops = [place(call, f"Stop {n}") for n in range(count)]
    for stop in stops:
        call("trip", "day", "1", "add", stop)
    route = call("trip", "map", "1")["days"][0]
    assert [stop["id"] for stop in route["stops"]] == stops[:5]
    assert [stop["id"] for stop in route["dropped_stops"]] == stops[5:]
    params = parse_qs(urlsplit(route["url"]).query)
    assert params["origin"] == ["Stop 0, Station, Osaka"]
    assert params["destination"] == ["Stop 4, Station, Osaka"]
    assert params["waypoints"] == ["|".join(f"Stop {n}, Station, Osaka" for n in (1, 2, 3))]
    assert "%7C" in route["url"]
    assert main(["trip", "map", "1"]) == 0
    output = capsys.readouterr().out
    assert len(output.splitlines()) == 1
    if count > 5:
        assert f"Omitted {count - 5} later stop(s)" in route["warning"]
        assert "3 waypoints (5 stops)" in output
    else:
        assert "warning" not in route and "Omitted" not in output


@pytest.mark.parametrize("day", ["0", "8", "-1"])
def test_map_validates_day(call, demo_trip, day):
    assert "Day must be between 1 and 7" in call("trip", "map", day, ok=False)["reason"]


def test_map_rejects_missing_wishlist_entry(call, demo_trip):
    store = Store()
    trip = store.read("trip")
    trip["days"]["1"] = ["w_missing"]
    store.write("trip", trip)
    assert "missing wishlist ID w_missing" in call("trip", "map", "1", ok=False)["reason"]


def test_map_rejects_url_over_api_length_limit(call, demo_trip):
    stop = place(call, "京" * 300)
    call("trip", "day", "1", "add", stop)
    assert "2048-character limit" in call("trip", "map", "1", ok=False)["reason"]


def test_map_real_module_entry_point(demo_trip, call):
    stop = place(call)
    call("trip", "day", "2", "add", stop)
    result = subprocess.run([sys.executable, "-m", "tripcrew", "trip", "map", "2", "--json"],
                            cwd=ROOT / "tools", capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["days"][0]["stops"][0]["id"] == stop
    assert data["days"][0]["url"].startswith("https://www.google.com/maps/search/?api=1&query=")

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

def test_write_activity_cards(call, activity_events):
    call("trip", "set", "--start", "2026-12-10", "--end", "2026-12-16", "--cities", "Osaka", "Kyoto",
         "--budget-sgd", "1500", "--categories", "flight=700", "other=800")
    assert activity_events == [
        {"type": "task", "from": "planner", "to": "you", "state": "finalised",
         "summary": "Trip: 10–16 Dec, Osaka + Kyoto"},
        {"type": "task", "from": "budget", "to": "you", "state": "finalised", "summary": "Budget S$1,500"}]
    activity_events.clear()
    stop = place(call, "Hiraoka Park")
    assert activity_events == [{"type": "task", "from": "reel_adder", "to": "planner",
                                "state": "delegated", "summary": "Hiraoka Park"}]
    activity_events.clear()
    call("trip", "day", "1", "add", stop)
    call("trip", "day", "1", "move", stop, "--to-day", "2")
    call("trip", "day", "2", "move", stop, "--position", "1")
    call("spend", "add", "12.14", "SGD", "--note", "ramen", "--day", "2", "--category", "other")
    assert activity_events == [
        {"type": "task", "from": "planner", "to": "you", "state": "finalised", "summary": f"Day {day}: Hiraoka Park"}
        for day in (1, 2, 2)] + [
        {"type": "task", "from": "budget", "to": "you", "state": "finalised", "summary": "S$12.14 · ramen"}]
    activity_events.clear()
    call("trip", "set", "--categories", "flight=600", "other=900")
    assert activity_events == [{"type": "task", "from": "budget", "to": "you",
                                "state": "finalised", "summary": "Budget S$1,500"}]


def test_reads_removals_and_failed_writes_do_not_post(call, demo_trip, activity_events, monkeypatch):
    stop = place(call)
    call("trip", "day", "1", "add", stop)
    activity_events.clear()
    call("trip", "show")
    call("wishlist", "list")
    call("spend", "list")
    call("budget", "status")
    call("trip", "set", "--interests", "food")
    call("trip", "day", "1", "add", stop, ok=False)
    call("trip", "set", "--budget-sgd", "-1", ok=False)
    call("wishlist", "add", "--name", " ", "--city", "Osaka", "--area", "North", "--category", "tip", ok=False)
    call("spend", "add", "-1", "SGD", "--note", "bad", ok=False)
    call("trip", "day", "1", "remove", stop)
    call("wishlist", "remove", stop)

    def failed_write(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Store, "write", failed_write)
    call("trip", "set", "--cities", "Tokyo", ok=False)
    call("wishlist", "add", "--name", "Park", "--city", "Osaka", "--area", "North", "--category", "tip", ok=False)
    call("spend", "add", "1", "SGD", "--note", "ramen", ok=False)
    assert activity_events == []


def test_reel_wishlist_has_only_identified_card(call, activity_events, monkeypatch):
    reels = []
    monkeypatch.setattr("tripcrew.reels.post_event", lambda step, **fields: reels.append({"step": step, **fields}))
    call("wishlist", "add", "--name", "Park", "--area", "North", "--city", "Osaka", "--category", "tip", "--reel")
    call("reel", "identified", "--place", "Park, North", "--platform", "instagram")
    assert activity_events == []
    assert reels == [{"step": "identified", "platform": "instagram", "place": "Park, North"}]


def test_activity_poster_contract_and_silent_failure(monkeypatch, capsys):
    from io import BytesIO

    requests = []

    def relay(request, timeout):
        requests.append((request, timeout))
        return BytesIO()

    monkeypatch.delenv("TRIPCREW_RELAY_URL", raising=False)
    monkeypatch.setattr("tripcrew.activity.urlopen", relay)
    payload = post_event("budget", "planner", "delegated", " Day 2\n over budget " + "x" * 100)
    request, timeout = requests[0]
    assert request.full_url == "http://127.0.0.1:8771/activity"
    assert request.get_method() == "POST" and timeout == 1
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == payload == {
        "type": "task", "from": "budget", "to": "planner", "state": "delegated",
        "summary": ("Day 2 over budget " + "x" * 100)[:80]}
    monkeypatch.setenv("TRIPCREW_RELAY_URL", "http://relay.test:8771/")
    post_event("budget", "you", "finalised", "S$12.14 · ramen")
    assert requests[-1][0].full_url == "http://relay.test:8771/activity"

    def offline(*args, **kwargs):
        raise OSError("relay absent")

    monkeypatch.setattr("tripcrew.activity.urlopen", offline)
    assert post_event("planner", "you", "finalised", "Day 2: Park")["summary"] == "Day 2: Park"
    monkeypatch.setenv("TRIPCREW_RELAY_URL", "invalid URL")
    post_event("planner", "you", "finalised", "Day 2: Park")
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_activity_offline_preserves_successful_write(call, monkeypatch):
    def offline(*args, **kwargs):
        raise TimeoutError("relay timed out")

    monkeypatch.setattr("tripcrew.activity.post_event", post_event)
    monkeypatch.setattr("tripcrew.activity.urlopen", offline)
    call("trip", "set", "--budget-sgd", "0")
    call("wishlist", "add", "--name", "Park", "--city", "Osaka", "--area", "North", "--category", "tip")
    call("spend", "add", "12.14", "SGD", "--note", "ramen")
    assert Store().read("trip")["budget_sgd"] == "0.00"
    assert Store().read("wishlist")[0]["name"] == "Park"
    assert Store().read("spend")[0]["amount_sgd"] == "12.14"


def test_partial_trip_settings_and_jpy_card(call, activity_events):
    from tripcrew import money

    call("trip", "set", "--start", "2026-12-10")
    call("trip", "set", "--cities", "Osaka")
    call("trip", "set", "--budget-sgd", "0")
    assert activity_events == [
        {"type": "task", "from": "planner", "to": "you", "state": "finalised", "summary": summary}
        for summary in ("Trip: 10 Dec", "Trip: 10 Dec, Osaka")] + [
        {"type": "task", "from": "budget", "to": "you", "state": "finalised", "summary": "Budget S$0"}]
    store = Store()
    with store.transaction():
        store.write("fx", {"base": "JPY", "quote": "SGD", "rate": "0.00809", "date": "2026-11-04",
                           "fetched_at": money.timestamp().isoformat()})
    activity_events.clear()
    call("spend", "add", "1500", "JPY", "--note", "ramen")
    assert activity_events == [{"type": "task", "from": "budget", "to": "you",
                                "state": "finalised", "summary": "S$12.14 · ramen"}]


def test_group_split_is_exact_and_settles_up(call, demo_trip):
    call("trip", "set", "--people", "Woo", "Ana", "Ben")
    dinner = call("spend", "add", "100", "SGD", "--note", "Dinner", "--day", "2", "--paid-by", "woo")["item"]
    assert dinner["paid_by"] == "Woo"
    assert dinner["split"] == {"Woo": "33.34", "Ana": "33.33", "Ben": "33.33"}
    call("spend", "add", "30", "SGD", "--note", "Taxi", "--day", "2", "--paid-by", "Ana", "--split", "Ana", "Ben")
    result = call("spend", "balances")
    assert {item["name"]: item["net_sgd"] for item in result["people"]} == {"Woo": "66.66", "Ana": "-18.33", "Ben": "-48.33"}
    assert result["transfers"] == [{"from": "Ben", "to": "Woo", "amount_sgd": "48.33"},
                                   {"from": "Ana", "to": "Woo", "amount_sgd": "18.33"}]
    assert result["unsplit_count"] == 0


def test_split_rejects_unknown_people_and_counts_unsplit_spend(call, demo_trip):
    call("spend", "add", "5", "SGD", "--note", "Snack", "--day", "1")
    assert call("spend", "balances") == {"ok": True, "people": [], "transfers": [], "unsplit_count": 1}
    assert not call("spend", "add", "5", "SGD", "--note", "X", "--paid-by", "Woo", ok=False)["ok"]
    call("trip", "set", "--people", "Woo", "Ana")
    assert not call("spend", "add", "5", "SGD", "--note", "X", "--paid-by", "Zed", ok=False)["ok"]
    assert not call("spend", "add", "5", "SGD", "--note", "X", "--paid-by", "Woo", "--split", "Zed", ok=False)["ok"]
    assert not call("spend", "add", "5", "SGD", "--note", "X", "--split", "Woo", ok=False)["ok"]
    assert len(call("spend", "list")["spend"]) == 1


def test_transcribe_returns_text_and_rejects_missing_or_silent_audio(call, tmp_path, monkeypatch):
    from tripcrew import reels
    voice = tmp_path / "voice.ogg"
    voice.write_bytes(b"audio")
    monkeypatch.setattr(reels, "speech_to_text", lambda path, language: f"Wagyu beef 3000 yen {language}")
    assert call("transcribe", str(voice))["transcript"] == "Wagyu beef 3000 yen en"
    assert "not found" in call("transcribe", str(tmp_path / "missing.ogg"), ok=False)["reason"]
    monkeypatch.setattr(reels, "speech_to_text", lambda path, language: "")
    assert "No speech" in call("transcribe", str(voice), ok=False)["reason"]
