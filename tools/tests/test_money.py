from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
import json

import pytest

from tripcrew import money
from tripcrew.store import Store


NOW = datetime(2026, 11, 4, 2, tzinfo=timezone.utc)


def cached(store, age=0):
    value = {"base": "JPY", "quote": "SGD", "rate": "0.028345",
             "date": "2026-11-03", "fetched_at": (NOW - timedelta(seconds=age)).isoformat()}
    with store.transaction():
        store.write("fx", value)
    return value


def test_live_fx_saved_and_used_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    calls = []

    def online(url, timeout):
        calls.append((url, timeout))
        return BytesIO(json.dumps({"base": "JPY", "date": "2026-11-03", "rates": {"SGD": 0.028345}}).encode())

    monkeypatch.setattr(money, "urlopen", online)
    store = Store(tmp_path)
    result = money.convert(store, "1500", "JPY", "SGD")
    assert result["converted"] == "42.52"
    assert result["fx"]["source"] == "live"
    assert calls == [(money.FX_URL, 10)]
    assert money.convert(store, "1500", "JPY", "SGD")["fx"]["source"] == "cache"
    assert len(calls) == 1
    assert store.read("fx")["rate"] == "0.028345"
    assert money.convert(store, "42.52", "SGD", "JPY")["converted"] == "1500.09"


@pytest.mark.parametrize("age,source", [(43199, "cache"), (43200, "stale_cache"), (86400, "stale_cache")])
def test_cache_expiry_and_offline_fallback(monkeypatch, tmp_path, age, source):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    store = Store(tmp_path)
    original = cached(store, age)

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(money, "urlopen", offline)
    result = money.rate(store)
    assert result["source"] == source
    assert result["age_seconds"] == age
    if source == "stale_cache":
        assert f"{age / 3600:.1f} hours ago" in result["warning"]
    assert store.read("fx") == original


def test_expired_cache_refreshes(monkeypatch, tmp_path):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    store = Store(tmp_path)
    cached(store, 43200)
    monkeypatch.setattr(money, "urlopen", lambda *a, **k: BytesIO(
        b'{"base":"JPY","date":"2026-11-04","rates":{"SGD":0.03}}'))
    assert money.rate(store)["rate"] == "0.03"
    assert store.read("fx")["fetched_at"] == NOW.isoformat()


def test_offline_without_cache_fails(monkeypatch, tmp_path):
    def offline(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(money, "urlopen", offline)
    with pytest.raises(ValueError, match="no cached rate"):
        money.convert(Store(tmp_path), 1500, "JPY", "SGD")


@pytest.mark.parametrize("body", [b'{}', b'bad json', b'{"base":"JPY","date":"2026-11-04","rates":{"SGD":0}}',
                                      b'{"base":"USD","date":"2026-11-04","rates":{"SGD":0.03}}'])
def test_invalid_api_response_never_becomes_a_rate(monkeypatch, tmp_path, body):
    monkeypatch.setattr(money, "urlopen", lambda *a, **k: BytesIO(body))
    store = Store(tmp_path)
    with pytest.raises(ValueError, match="no cached rate"):
        money.rate(store)
    assert store.read("fx") == {}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "nope"])
def test_invalid_amounts(value):
    with pytest.raises(ValueError):
        money.number(value)


def test_same_currency_requires_no_rate(tmp_path):
    assert money.convert(Store(tmp_path), "15.25", "SGD", "SGD")["converted"] == "15.25"


def test_budget_math_and_historical_fx(call, monkeypatch, demo_trip):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    store = Store()
    cached(store)
    call("spend", "add", "1500", "JPY", "--note", "lunch", "--day", "1")
    call("spend", "add", "10.05", "SGD", "--note", "train", "--day", "1")
    call("spend", "add", "100", "SGD", "--note", "hotel", "--day", "2")
    with store.transaction():
        cache = store.read("fx")
        cache["rate"] = "0.99"
        store.write("fx", cache)
    result = call("budget", "status")
    assert result["totals"] == {"budget_sgd": "6000.00", "spent_sgd": "152.57", "left_sgd": "5847.43"}
    assert sum(Decimal(day["budget_sgd"]) for day in result["days"]) == Decimal("6000.00")
    assert result["days"][0]["budget_sgd"] == "857.15"
    assert result["days"][1]["budget_sgd"] == "857.15"
    assert result["days"][2]["budget_sgd"] == "857.14"
    assert result["days"][0]["spent_sgd"] == "52.57"
    assert result["days"][0]["spend"][0]["amount"] == "1500"
    assert result["days"][0]["spend"][0]["fx"]["rate"] == "0.028345"
    filtered = call("budget", "status", "--day", "2")
    assert len(filtered["days"]) == 1
    assert filtered["days"][0]["left_sgd"] == "757.15"
    assert filtered["totals"] == result["totals"]


def test_overspend_is_negative_and_tiny_budget_allocates_exactly(call, demo_trip):
    call("trip", "set", "--budget-sgd", "0.03")
    call("spend", "add", "0.05", "SGD", "--note", "overspent", "--day", "1")
    result = call("budget", "status")
    assert result["totals"]["left_sgd"] == "-0.02"
    assert result["days"][0]["left_sgd"] == "-0.04"
    assert [day["budget_sgd"] for day in result["days"]] == ["0.01"] * 3 + ["0.00"] * 4


def test_budget_categories_track_spend_and_warn_at_80_percent(call, monkeypatch, demo_trip):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    cached(Store())
    call("trip", "set", "--budget-sgd", "1500", "--categories", "flight=700", "other=800", ok=True)
    assert call("trip", "set", "--categories", "flight=700", "other=700", ok=False)["reason"].startswith(
        "Categories add up to SGD 1400")
    assert "flight, other" in call("spend", "add", "5", "SGD", "--note", "snack", ok=False)["reason"]
    call("spend", "add", "620", "SGD", "--note", "flight", "--category", "Flight")
    call("spend", "add", "1500", "JPY", "--note", "lunch", "--day", "1", "--category", "other")
    result = call("budget", "status")
    flight, other = result["categories"]
    assert flight == {"category": "flight", "budget_sgd": "700.00", "spent_sgd": "620.00",
                      "left_sgd": "80.00", "used_percent": 88, "warning": True}
    assert other["spent_sgd"] == "42.52" and other["warning"] is False
    assert result["totals"]["spent_sgd"] == "662.52"
    assert result["days"][0]["spent_sgd"] == "42.52"
    assert call("spend", "list")["spend"][0]["day"] is None


def estimated_stop(call, name, price=None, day=1):
    args = ["wishlist", "add", "--name", name, "--area", "Station", "--city", "Osaka", "--category", "food"]
    if price is not None:
        args += ["--price-jpy", str(price)]
    stop = call(*args)["item"]["id"]
    if day is not None:
        call("trip", "day", str(day), "add", stop)
    return stop


def test_day_check_negotiation_categories_unknowns_and_historical_spend(call, monkeypatch, demo_trip):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    store = Store()
    cached(store)
    call("trip", "set", "--budget-sgd", "1500", "--categories", "flight=700", "other=800")
    pricey = estimated_stop(call, "Lunch", 5000)
    cheap = estimated_stop(call, "Nearby lunch", 1000, day=None)
    free = estimated_stop(call, "Park", 0)
    unknown = estimated_stop(call, "Market")
    estimated_stop(call, "Tomorrow", 100, day=2)
    estimated_stop(call, "Unplanned expensive", 999999, day=None)
    call("spend", "add", "1000", "JPY", "--note", "Train", "--day", "1", "--category", "other")
    call("spend", "add", "620", "SGD", "--note", "Flight", "--category", "flight")
    cached_value = cached(store)
    cached_value["rate"] = "0.03"
    store.write("fx", cached_value)
    before = {name: store.read(name) for name in ("trip", "wishlist", "spend")}
    result = call("budget", "check")
    assert [day["day"] for day in result["days"]] == [1, 2]
    day = result["days"][0]
    assert day["estimate_jpy"] == "5000" and day["estimate_sgd"] == "150.00"
    assert day["actual_sgd"] == "28.35" and day["total_sgd"] == "178.35"
    assert day["allowance_sgd"] == "114.29" and day["difference_sgd"] == "64.06"
    assert day["status"] == "over" and day["over_budget"] is True
    assert day["unknown_count"] == 1 and day["complete"] is False
    assert day["unknown_stops"] == [{"id": unknown, "name": "Market"}]
    assert [item["id"] for item in day["most_expensive_stops"]] == [pricey, free]
    assert {name: store.read(name) for name in before} == before
    call("trip", "day", "1", "remove", pricey)
    call("trip", "day", "1", "add", cheap)
    checked = call("budget", "check", "--day", "1")["days"]
    assert len(checked) == 1
    assert checked[0]["status"] == "under" and checked[0]["over_budget"] is False
    assert checked[0]["difference_sgd"] == "-55.94"


def test_day_check_no_categories_rounding_ranking_and_explicit_empty_day(call, monkeypatch, demo_trip):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    cached(Store())
    call("trip", "set", "--budget-sgd", "0.03")
    assert call("budget", "check")["days"] == []
    assert [call("budget", "check", "--day", str(day))["days"][0]["allowance_sgd"]
            for day in range(1, 8)] == ["0.01"] * 3 + ["0.00"] * 4
    ids = [estimated_stop(call, str(price), price) for price in (20, 40, 10, 30)]
    day = call("budget", "check", "--day", "1")["days"][0]
    assert day["estimate_sgd"] == "2.83" and day["difference_sgd"] == "2.82"
    assert [item["id"] for item in day["most_expensive_stops"]] == [ids[1], ids[3], ids[0]]
    assert day["complete"] is True
    for invalid in ("0", "8"):
        assert "between 1 and 7" in call("budget", "check", "--day", invalid, ok=False)["reason"]


def test_day_check_free_unknown_and_zero_allowance_need_no_fx(call, demo_trip):
    call("trip", "set", "--budget-sgd", "0")
    estimated_stop(call, "Free", 0)
    estimated_stop(call, "Unknown")
    result = call("budget", "check")
    day = result["days"][0]
    assert day["status"] == "at_allowance" and day["over_budget"] is False
    assert day["unknown_count"] == 1 and day["complete"] is False
    assert day["estimate_sgd"] == "0.00" and result["fx"] is None
    call("trip", "set", "--budget-sgd", "100", "--categories", "flight=100")
    call("spend", "add", "1", "SGD", "--note", "Day flight", "--day", "1", "--category", "flight")
    day = call("budget", "check")["days"][0]
    assert day["allowance_sgd"] == "0.00" and day["actual_sgd"] == "1.00"
    assert day["status"] == "over"


def test_day_check_rounds_day_sum_once(call, monkeypatch, demo_trip):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    store = Store()
    rate = cached(store)
    rate["rate"] = "0.005"
    store.write("fx", rate)
    estimated_stop(call, "First", 1)
    estimated_stop(call, "Second", 1)
    assert call("budget", "check")["days"][0]["estimate_sgd"] == "0.01"


@pytest.mark.parametrize("source", ["live", "cache", "stale_cache", "unavailable"])
def test_day_check_fx_sources_and_failure(call, monkeypatch, demo_trip, source, capsys):
    from tripcrew.cli import main

    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    estimated_stop(call, "Lunch", 1500)
    estimated_stop(call, "Train", 500)
    estimated_stop(call, "Tomorrow", 500, day=2)
    if source in ("cache", "stale_cache"):
        cached(Store(), 86400 if source == "stale_cache" else 0)
    requests = []

    def fetch(*a, **k):
        requests.append(a)
        if source == "live":
            return BytesIO(b'{"base":"JPY","date":"2026-11-04","rates":{"SGD":0.03}}')
        raise OSError("offline")

    monkeypatch.setattr(money, "urlopen", fetch)
    if source == "unavailable":
        assert "no cached rate" in call("budget", "check", ok=False)["reason"]
        return
    result = call("budget", "check")
    assert result["fx"]["source"] == source
    assert len(requests) == (0 if source == "cache" else 1)
    if source == "stale_cache":
        assert "24.0 hours ago" in result["fx"]["warning"]
    assert main(["budget", "check"]) == 0
    output = capsys.readouterr().out
    assert all(line.startswith("*") for line in output.splitlines())
    assert "UNDER by SGD" in output and "*Most expensive*" in output
    if source == "stale_cache":
        assert "Offline: using cached FX" in output


def test_price_and_over_budget_day_send_budget_cards(call, monkeypatch, demo_trip, activity_events):
    monkeypatch.setattr(money, "timestamp", lambda: NOW)
    cached(Store())
    call("trip", "set", "--budget-sgd", "1500", "--categories", "flight=700", "other=800")
    stop = call("wishlist", "add", "--name", "Kobe beef", "--area", "Namba", "--city", "Osaka",
                "--category", "food", "--reel")["item"]["id"]
    call("trip", "day", "2", "add", stop)
    activity_events.clear()
    call("wishlist", "price", stop, "--price-jpy", "20000", "--source-note", "menu")
    assert call("budget", "check", "--day", "2")["days"][0]["over_budget"] is True
    assert activity_events == [
        {"type": "task", "from": "budget", "to": "planner", "state": "finalised", "summary": "Kobe beef: ¥20000"},
        {"type": "task", "from": "budget", "to": "planner", "state": "delegated", "summary": "Day 2 over by S$452.61"}]


def test_pre_trip_spend_survives_date_change(call, demo_trip):
    call("trip", "set", "--budget-sgd", "1500", "--categories", "flight=700", "other=800")
    call("spend", "add", "620", "SGD", "--note", "flight", "--category", "flight")
    assert call("trip", "set", "--end", "2026-12-15")["trip"]["end"] == "2026-12-15"
