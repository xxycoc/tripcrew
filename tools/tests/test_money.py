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
