import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

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
