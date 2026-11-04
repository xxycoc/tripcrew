import json
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


def test_itinerary_lifecycle_and_wishlist_filters(call):
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


def test_invalid_moves_leave_state_unchanged(call):
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


def test_trip_set_preserves_stops_and_validates_dates(call):
    stop = place(call)
    call("trip", "day", "7", "add", stop)
    call("trip", "set", "--cities", "Osaka", "Kyoto", "--interests", "food", "culture", "--budget-myr", "6500")
    changed = call("trip", "show")["trip"]
    assert changed["days"]["7"] == [stop]
    assert changed["budget_myr"] == "6500.00"
    assert changed["interests"] == ["food", "culture"]
    for args in [("--end", "2026-12-11"), ("--end", "2026-12-01"), ("--start", "nonsense"),
                 ("--budget-myr", "1.001"), ("--budget-myr", "-1")]:
        call("trip", "set", *args, ok=False)
        assert Store().read("trip") == changed


def test_dates_cannot_exclude_spending(call):
    call("spend", "add", "100", "MYR", "--note", "hotel", "--day", "7")
    call("trip", "set", "--end", "2026-12-15", ok=False)
    assert call("spend", "list")["spend"][0]["day"] == 7


def test_wishlist_unknown_price_and_unverified(call):
    result = call("wishlist", "add", "--name", "Park", "--area", "North", "--city", "Osaka", "--category", "tip")
    assert result["item"]["price_jpy"] is None
    assert result["item"]["verified"] is False


@pytest.mark.parametrize("args", [("spend", "add", "0", "MYR", "--note", "bad", "--day", "1"),
                                 ("spend", "add", "1.005", "MYR", "--note", "bad", "--day", "1"),
                                 ("spend", "add", "100", "JPY", "--note", "bad", "--day", "0"),
                                 ("budget", "status", "--day", "8"),
                                 ("trip", "set"), ("wishlist", "remove", "unknown"),
                                 ("reel", "failed", "--reason", " "), ("no-such-command",)])
def test_validation_json(call, args):
    call(*args, ok=False)


def test_human_lines_have_telegram_labels_no_tables_or_newline_injection(call, capsys):
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


def test_real_module_entry_point(tmp_path):
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
