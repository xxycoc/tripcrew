import json
import subprocess
import sys

import pytest

from tripcrew.cli import main
from tripcrew.store import ROOT, Store


EMPTY_TRIP = {"start": None, "end": None, "cities": [], "budget_sgd": None,
              "interests": [], "days": {}}


def test_fresh_trip_show_is_empty_and_explains_setup(call, capsys):
    assert call("trip", "show")["trip"] == EMPTY_TRIP
    assert main(["trip", "show"]) == 0
    output = capsys.readouterr().out
    assert "No trip is set yet" in output
    assert "trip set" in output
    for flag in ("--start", "--end", "--cities", "--budget-sgd", "--interests"):
        assert flag in output
    assert "*Day" not in output
    assert "None" not in output
    assert not (Store().root / "trip.json").exists()


@pytest.mark.parametrize("settings,missing", [
    ([], ["Budget isn't set yet", "Trip dates aren't set yet"]),
    (["--budget-sgd", "6000"], ["Trip dates aren't set yet"]),
    (["--start", "2026-12-10", "--end", "2026-12-16"], ["Budget isn't set yet"]),
    (["--budget-sgd", "0", "--start", "2026-12-10"], ["Trip dates aren't set yet"]),
    (["--budget-sgd", "0", "--end", "2026-12-16"], ["Trip dates aren't set yet"]),
])
@pytest.mark.parametrize("day", [[], ["--day", "1"]])
@pytest.mark.parametrize("action", ["status", "check"])
def test_budget_requires_budget_and_dates(call, capsys, settings, missing, day, action):
    if settings:
        call("trip", "set", *settings)
    before = Store().read("trip")
    result = call("budget", action, *day, ok=False)
    for reason in missing:
        assert reason in result["reason"]
    assert "trip set" in result["reason"]
    assert "totals" not in result and "days" not in result
    assert main(["budget", action, *day]) == 1
    output = capsys.readouterr().out
    for reason in missing:
        assert reason in output
    assert "*Total*" not in output and "*Day" not in output
    assert Store().read("trip") == before


@pytest.mark.parametrize("settings", [[], ["--start", "2026-12-10"], ["--end", "2026-12-16"]])
@pytest.mark.parametrize("operation", ["add", "remove", "move"])
def test_itinerary_requires_both_dates_without_changing_state(call, capsys, settings, operation):
    if settings:
        call("trip", "set", *settings)
    before = Store().read("trip")
    args = ["trip", "day", "1", operation, "w_missing"]
    result = call(*args, ok=False)
    assert "Trip dates aren't set yet" in result["reason"]
    assert "trip set --start YYYY-MM-DD --end YYYY-MM-DD" in result["reason"]
    assert main(args) == 1
    assert "Trip dates aren't set yet" in capsys.readouterr().out
    assert Store().read("trip") == before


@pytest.mark.parametrize("currency", ["JPY", "SGD"])
def test_spending_requires_dates_before_conversion(call, currency):
    result = call("spend", "add", "100", currency, "--note", "lunch", "--day", "1", ok=False)
    assert "Trip dates aren't set yet" in result["reason"]
    assert call("spend", "list")["spend"] == []
    assert Store().read("fx") == {}


@pytest.mark.parametrize("first_date,second_date", [("start", "end"), ("end", "start")])
def test_trip_can_be_configured_incrementally(call, capsys, first_date, second_date):
    trip = call("trip", "set", "--budget-sgd", "0")["trip"]
    assert trip == {**EMPTY_TRIP, "budget_sgd": "0.00"}
    trip = call("trip", "set", "--cities", "Tokyo", "--interests", "food")["trip"]
    assert trip == {**EMPTY_TRIP, "budget_sgd": "0.00", "cities": ["Tokyo"], "interests": ["food"]}
    dates = {"start": "2026-12-10", "end": "2026-12-11"}
    trip = call("trip", "set", f"--{first_date}", dates[first_date])["trip"]
    assert trip[first_date] == dates[first_date] and trip[second_date] is None
    assert main(["trip", "show"]) == 0
    output = capsys.readouterr().out
    assert "not set" in output and "None" not in output and "*Day" not in output
    trip = call("trip", "set", f"--{second_date}", dates[second_date])["trip"]
    assert trip == {**EMPTY_TRIP, **dates, "budget_sgd": "0.00", "cities": ["Tokyo"], "interests": ["food"]}
    result = call("budget", "status")
    assert result["totals"] == {"budget_sgd": "0.00", "spent_sgd": "0.00", "left_sgd": "0.00"}
    assert len(result["days"]) == 2
    assert [day["budget_sgd"] for day in result["days"]] == ["0.00", "0.00"]


@pytest.mark.parametrize("settings", [
    ["--start", "nonsense"], ["--end", "2026-02-30"],
    ["--start", "2026-12-11", "--end", "2026-12-10"],
    ["--budget-sgd", "1.001"], ["--budget-sgd", "-1"], ["--cities", " "],
])
def test_invalid_initial_settings_leave_trip_empty(call, settings):
    call("trip", "set", *settings, ok=False)
    assert Store().read("trip") == EMPTY_TRIP
    assert not (Store().root / "trip.json").exists()


def test_wishlist_and_fx_work_before_trip_setup(call):
    assert call("wishlist", "list", "--unplanned")["wishlist"] == []
    item = call("wishlist", "add", "--name", "Park", "--area", "North", "--city", "Tokyo",
                "--category", "attraction")["item"]
    assert call("wishlist", "list", "--unplanned")["wishlist"] == [item]
    call("wishlist", "remove", item["id"])
    assert call("wishlist", "list")["wishlist"] == []
    assert call("fx", "convert", "10", "SGD", "SGD")["converted"] == "10.00"
    assert Store().read("trip") == EMPTY_TRIP


@pytest.mark.parametrize("args,code", [
    (["trip", "show"], 0), (["budget", "status"], 1),
    (["budget", "status", "--day", "1"], 1), (["trip", "day", "1", "add", "w_missing"], 1),
])
def test_empty_trip_through_real_module(args, code):
    result = subprocess.run([sys.executable, "-m", "tripcrew", *args, "--json"],
                            cwd=ROOT / "tools", capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == code, result.stderr
    assert not result.stderr
    data = json.loads(result.stdout)
    assert data["ok"] is (code == 0)
    if code == 0:
        assert data["trip"] == EMPTY_TRIP
    else:
        assert "aren't set yet" in data["reason"]


@pytest.mark.parametrize("settings", [[], ["--start", "2026-12-10"], ["--end", "2026-12-16"]])
@pytest.mark.parametrize("day", [[], ["1"]])
def test_map_requires_dates(call, settings, day):
    if settings:
        call("trip", "set", *settings)
    before = Store().read("trip")
    assert "Trip dates aren't set yet" in call("trip", "map", *day, ok=False)["reason"]
    assert Store().read("trip") == before
