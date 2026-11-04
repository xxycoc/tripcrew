from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from urllib.request import urlopen


FX_URL = "https://api.frankfurter.dev/v1/latest?base=JPY&symbols=MYR"
TTL = 12 * 60 * 60


def number(value, *, positive=False):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Amount must be a finite number.") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError("Amount must be positive." if positive else "Amount must be zero or greater.")
    return result


def cents(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def timestamp():
    return datetime.now(timezone.utc)


def rate(store):
    with store.transaction():
        cached = store.read("fx")
        age = None
        if cached:
            try:
                fetched = datetime.fromisoformat(cached["fetched_at"])
                age = (timestamp() - fetched).total_seconds()
                number(cached["rate"], positive=True)
                if cached["base"] != "JPY" or cached["quote"] != "MYR" or age < 0:
                    raise ValueError("invalid cache")
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("Invalid fx.json cache; repair or remove it before converting.") from exc
            if age < TTL:
                return {**cached, "source": "cache", "age_seconds": int(age), "warning": None}
        try:
            with urlopen(FX_URL, timeout=10) as response:
                data = json.load(response)
            if data["base"] != "JPY":
                raise ValueError("Unexpected FX base")
            value = number(data["rates"]["MYR"], positive=True)
            datetime.strptime(data["date"], "%Y-%m-%d")
            fresh = {"base": "JPY", "quote": "MYR", "rate": str(value),
                     "date": data["date"], "fetched_at": timestamp().isoformat()}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if not cached:
                raise ValueError("FX unavailable and no cached rate exists; no conversion was made.") from exc
            warning = f"Offline: using cached FX fetched {age / 3600:.1f} hours ago (rate date {cached['date']})."
            return {**cached, "source": "stale_cache", "age_seconds": int(age), "warning": warning}
        store.write("fx", fresh)
        return {**fresh, "source": "live", "age_seconds": 0, "warning": None}


def convert(store, amount, source, target):
    amount = number(amount)
    source, target = source.upper(), target.upper()
    if source not in {"JPY", "MYR"} or target not in {"JPY", "MYR"}:
        raise ValueError("Supported currencies: JPY and MYR.")
    fx = None
    result = amount
    if source != target:
        fx = rate(store)
        factor = Decimal(fx["rate"])
        result = amount * factor if source == "JPY" else amount / factor
    return {"amount": str(amount), "from": source, "to": target,
            "converted": str(cents(result)), "fx": fx}
