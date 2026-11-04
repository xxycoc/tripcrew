import json
import os
from pathlib import Path
import subprocess
import sys

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
