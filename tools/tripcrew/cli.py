import argparse
from datetime import date
from decimal import Decimal
import json
import sys
from uuid import uuid4

from . import money, reels
from .store import Store


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def parser():
    root = Parser(description="Shared TripCrew state. Add --json anywhere for machine output. "
                  "Planner owns itinerary; Budget owns prices/spend; Reel Adder owns verified wishlist entries.")
    root.add_argument("--json", action="store_true", help="Emit JSON; reel fetch always emits JSON.")
    groups = root.add_subparsers(dest="group", required=True)

    trip = groups.add_parser("trip", help="Read trip settings or edit itinerary.")
    commands = trip.add_subparsers(dest="action", required=True)
    commands.add_parser("show", help="Read settings and ordered stops, without prices.")
    setting = commands.add_parser("set", help="Change only supplied settings; preserve itinerary.")
    setting.add_argument("--start", help="First date, YYYY-MM-DD (inclusive).")
    setting.add_argument("--end", help="Last date, YYYY-MM-DD (inclusive).")
    setting.add_argument("--cities", nargs="+", help="Replace cities; quote multiword names.")
    setting.add_argument("--budget-myr", help="Total MYR budget, at most two decimal places.")
    setting.add_argument("--interests", nargs="+", help="Replace interests; quote multiword interests.")
    day = commands.add_parser("day", help="Ordered wishlist references; positions start at 1.")
    day.add_argument("day", type=int, help="Trip day, starting at 1.")
    operations = day.add_subparsers(dest="operation", required=True)
    for operation in ("add", "remove", "move"):
        stop = operations.add_parser(operation, help={
            "add": "Add a wishlist ID, appending unless --position is supplied.",
            "remove": "Remove a wishlist ID from this day.",
            "move": "Move a wishlist ID to its final position, optionally to another day.",
        }[operation])
        stop.add_argument("id", help="Wishlist ID.")
        if operation != "remove":
            stop.add_argument("--position", type=int, help="Final 1-based position; default append.")
        if operation == "move":
            stop.add_argument("--to-day", type=int, help="Destination day; default same day.")

    wishlist = groups.add_parser("wishlist", help="Keep source-backed places and travel tips.")
    commands = wishlist.add_subparsers(dest="action", required=True)
    add = commands.add_parser("add", help="Add a place; --verified means the agent checked its source.")
    for name in ("name", "area", "city"):
        add.add_argument(f"--{name}", required=True)
    add.add_argument("--category", choices=["food", "attraction", "tip"], required=True)
    add.add_argument("--price-jpy", help="Estimated JPY price; omit when unknown, use 0 when free.")
    add.add_argument("--hours", default="", help="Opening hours, or leave unknown.")
    add.add_argument("--url", default="", help="Source URL.")
    add.add_argument("--verified", action="store_true", help="Mark externally verified.")
    add.add_argument("--note", default="")
    listing = commands.add_parser("list", help="Filter saved places; --unplanned excludes all itinerary stops.")
    listing.add_argument("--city")
    listing.add_argument("--category", choices=["food", "attraction", "tip"])
    listing.add_argument("--unplanned", action="store_true")
    remove = commands.add_parser("remove", help="Remove a place after removing its itinerary references.")
    remove.add_argument("id")

    spend = groups.add_parser("spend", help="Record actual spending. JPY entries keep the original and FX used.")
    commands = spend.add_subparsers(dest="action", required=True)
    add = commands.add_parser("add", help="Record one expense; stores MYR value at entry time.")
    add.add_argument("amount")
    add.add_argument("currency", type=str.upper, choices=["JPY", "MYR"])
    add.add_argument("--note", required=True)
    add.add_argument("--day", type=int, required=True)
    commands.add_parser("list", help="List expenses with original currency and booked MYR amounts.")

    budget = groups.add_parser("budget", help="Budget and actual spending in MYR; does not edit itinerary.")
    commands = budget.add_subparsers(dest="action", required=True)
    status = commands.add_parser("status", help="Total and daily budget/spent/left. Extra cents go to earliest days.")
    status.add_argument("--day", type=int, help="Show only this day's detail, plus trip totals.")

    fx = groups.add_parser("fx", help="Frankfurter JPY/MYR conversion; 12-hour cache, explicit stale fallback.")
    commands = fx.add_subparsers(dest="action", required=True)
    conversion = commands.add_parser("convert", help="Convert JPY or MYR; never substitutes an invented rate.")
    conversion.add_argument("amount")
    conversion.add_argument("source", type=str.upper, choices=["JPY", "MYR"])
    conversion.add_argument("target", type=str.upper, choices=["JPY", "MYR"])

    reel = groups.add_parser("reel", help="Extract metadata, then let the agent verify the place by web search.")
    commands = reel.add_subparsers(dest="action", required=True)
    fetch = commands.add_parser("fetch", help="Always prints JSON. Short captions trigger temporary audio transcription.")
    fetch.add_argument("url")
    fetch.add_argument("--audio", action="store_true", help="Force audio-only download and CPU/int8 transcription.")
    identified = commands.add_parser("identified", help="Post after the agent has verified the place.")
    identified.add_argument("--place", required=True)
    failed = commands.add_parser("failed", help="Post only after the agent decides it cannot identify the place.")
    failed.add_argument("--reason", required=True)
    for event in (identified, failed):
        event.add_argument("--platform", choices=["tiktok", "instagram"], help="Original platform, if known.")
    return root


def text(value):
    return " ".join(str(value).split())


def day_count(trip):
    count = (date.fromisoformat(trip["end"]) - date.fromisoformat(trip["start"])).days + 1
    if count <= 0:
        raise ValueError("Trip end must be on or after its start.")
    return count


def check_day(trip, day):
    if not 1 <= day <= day_count(trip):
        raise ValueError(f"Day must be between 1 and {day_count(trip)}.")


def new_id(prefix, entries):
    existing = {entry["id"] for entry in entries}
    while True:
        value = prefix + uuid4().hex[:12]
        if value not in existing:
            return value


def fx_lines(fx):
    if not fx:
        return []
    if fx.get("warning"):
        return [f"*FX* {fx['warning']}"]
    return [f"*FX* 1 JPY = {fx['rate']} MYR; rate date {fx['date']}; "
            f"{fx['source']}, fetched {fx['age_seconds'] / 3600:.1f} hours ago."]


def wishlist_line(item):
    price = "price unknown" if item["price_jpy"] is None else f"JPY {item['price_jpy']} estimated"
    return (f"*{item['id']}* {text(item['name'])}, {text(item['area'])}, {text(item['city'])}; "
            f"{item['category']}; {price}; {'verified' if item['verified'] else 'unverified'}"
            + (f"; hours: {text(item['hours'])}" if item['hours'] else "")
            + (f"; {text(item['source_url'])}" if item['source_url'] else "")
            + (f"; {text(item['note'])}" if item['note'] else ""))


def spend_line(item):
    original = f" (JPY {item['amount']})" if item["currency"] == "JPY" else ""
    return f"*{item['id']}* Day {item['day']}: MYR {item['amount_myr']}{original}; {text(item['note'])}"


def trip_command(args, store):
    with store.transaction():
        trip = store.read("trip")
        wishlist = store.read("wishlist")
        if args.action == "set":
            supplied = [args.start, args.end, args.cities, args.budget_myr, args.interests]
            if all(value is None for value in supplied):
                raise ValueError("Supply at least one trip setting; see trip set --help.")
            for key in ("start", "end", "cities", "interests"):
                value = getattr(args, key)
                if value is not None:
                    if isinstance(value, list) and any(not part.strip() for part in value):
                        raise ValueError(f"{key} cannot contain empty values.")
                    trip[key] = value
            count = day_count(trip)
            if any(int(day) > count and stops for day, stops in trip["days"].items()):
                raise ValueError("New dates would discard planned days; remove or move those stops first.")
            if any(item["day"] > count for item in store.read("spend")):
                raise ValueError("New dates would exclude recorded spending; keep those days in the trip.")
            trip["days"] = {day: stops for day, stops in trip["days"].items() if int(day) <= count}
            if args.budget_myr is not None:
                amount = money.number(args.budget_myr)
                if money.cents(amount) != amount:
                    raise ValueError("MYR budget must have at most two decimal places.")
                trip["budget_myr"] = str(money.cents(amount))
            store.write("trip", trip)
        elif args.action == "day":
            check_day(trip, args.day)
            stops = trip["days"].setdefault(str(args.day), [])
            if args.operation == "add":
                if args.id not in {item["id"] for item in wishlist}:
                    raise ValueError("Unknown wishlist ID.")
                if args.id in stops:
                    raise ValueError("That stop is already on this day; use move to reorder it.")
                target = stops
            else:
                if args.id not in stops:
                    raise ValueError("That stop is not on this day.")
                stops.remove(args.id)
                destination = getattr(args, "to_day", None)
                destination = args.day if destination is None else destination
                check_day(trip, destination)
                target = trip["days"].setdefault(str(destination), [])
                if args.operation == "move" and args.id in target:
                    raise ValueError("That stop is already on the destination day.")
            if args.operation != "remove":
                position = args.position if args.position is not None else len(target) + 1
                if not 1 <= position <= len(target) + 1:
                    raise ValueError(f"Position must be between 1 and {len(target) + 1}.")
                target.insert(position - 1, args.id)
            store.write("trip", trip)
    names = {item["id"]: item["name"] for item in wishlist}
    lines = [f"*Trip* {trip['start']} to {trip['end']}; {', '.join(map(text, trip['cities']))}",
             f"*Interests* {', '.join(map(text, trip['interests'])) or 'not set'}"]
    for day in range(1, day_count(trip) + 1):
        stops = trip["days"].get(str(day), [])
        lines.append(f"*Day {day}* " + (" → ".join(f"{stop} {text(names.get(stop, '(missing wishlist entry)'))}"
                                                for stop in stops) or "unplanned"))
    return {"trip": trip}, lines


def wishlist_command(args, store):
    with store.transaction():
        entries = store.read("wishlist")
        trip = store.read("trip")
        planned = {stop for stops in trip["days"].values() for stop in stops}
        if args.action == "add":
            if not all(getattr(args, key).strip() for key in ("name", "area", "city")):
                raise ValueError("Name, area and city cannot be blank.")
            item = {"id": new_id("w_", entries), "name": args.name, "area": args.area,
                    "city": args.city, "category": args.category,
                    "price_jpy": str(money.number(args.price_jpy)) if args.price_jpy is not None else None,
                    "hours": args.hours, "source_url": args.url, "verified": args.verified, "note": args.note}
            entries.append(item)
            store.write("wishlist", entries)
            return {"item": item}, [wishlist_line(item)]
        if args.action == "remove":
            if args.id in planned:
                raise ValueError("Place is on the itinerary; remove its stops before removing the wishlist entry.")
            remaining = [entry for entry in entries if entry["id"] != args.id]
            if len(remaining) == len(entries):
                raise ValueError("Unknown wishlist ID.")
            store.write("wishlist", remaining)
            return {"removed": args.id}, [f"*Removed* {args.id}"]
        entries = [entry for entry in entries
                   if (not args.city or entry["city"].casefold() == args.city.casefold())
                   and (not args.category or entry["category"] == args.category)
                   and (not args.unplanned or entry["id"] not in planned)]
    return {"wishlist": entries}, [wishlist_line(item) for item in entries] or ["*Wishlist* empty"]


def spend_command(args, store):
    if args.action == "list":
        with store.transaction():
            entries = store.read("spend")
        return {"spend": entries}, [spend_line(item) for item in entries] or ["*Spend* no expenses"]
    amount = money.number(args.amount, positive=True)
    if args.currency == "MYR" and money.cents(amount) != amount:
        raise ValueError("MYR spending must have at most two decimal places.")
    if not args.note.strip():
        raise ValueError("Spend note cannot be blank.")
    with store.transaction():
        check_day(store.read("trip"), args.day)
    conversion = money.convert(store, amount, args.currency, "MYR")
    with store.transaction():
        check_day(store.read("trip"), args.day)
        entries = store.read("spend")
        item = {"id": new_id("s_", entries), "amount": str(amount), "currency": args.currency,
                "amount_myr": conversion["converted"], "note": args.note, "day": args.day,
                "fx": conversion["fx"], "created_at": money.timestamp().isoformat()}
        entries.append(item)
        store.write("spend", entries)
    return {"item": item}, [spend_line(item), *fx_lines(item["fx"])]


def budget_command(args, store):
    with store.transaction():
        trip, entries = store.read("trip"), store.read("spend")
    count = day_count(trip)
    if args.day is not None:
        check_day(trip, args.day)
    total_budget = money.cents(money.number(trip["budget_myr"]))
    total_spent = sum((Decimal(item["amount_myr"]) for item in entries), Decimal("0.00"))
    totals = {"budget_myr": str(total_budget), "spent_myr": str(total_spent),
              "left_myr": str(total_budget - total_spent)}
    base, extra = divmod(int(total_budget * 100), count)
    days = []
    for day in range(1, count + 1):
        day_budget = Decimal(base + (day <= extra)) / 100
        expenses = [item for item in entries if item["day"] == day]
        spent = sum((Decimal(item["amount_myr"]) for item in expenses), Decimal("0.00"))
        days.append({"day": day, "budget_myr": str(money.cents(day_budget)), "spent_myr": str(spent),
                     "left_myr": str(money.cents(day_budget - spent)), "spend": expenses})
    selected = [day for day in days if args.day is None or day["day"] == args.day]
    lines = [f"*Total* MYR {totals['budget_myr']} budget; {totals['spent_myr']} spent; {totals['left_myr']} left"]
    for day in selected:
        originals = [f"JPY {item['amount']} → MYR {item['amount_myr']}" for item in day["spend"]
                     if item["currency"] == "JPY"]
        lines.append(f"*Day {day['day']}* MYR {day['budget_myr']} budget; {day['spent_myr']} spent; "
                     f"{day['left_myr']} left" + (f" ({'; '.join(originals)})" if originals else ""))
    return {"totals": totals, "days": selected}, lines


def dispatch(args):
    if args.group == "reel":
        if args.action == "fetch":
            data = reels.fetch(args.url, args.audio)
            return data, []
        fields = {"platform": args.platform}
        fields["place" if args.action == "identified" else "reason"] = (
            args.place if args.action == "identified" else args.reason)
        if not next(value for key, value in fields.items() if key != "platform").strip():
            raise ValueError("Place or reason cannot be blank.")
        event = reels.post_event(args.action, **fields)
        return {"event": event, "delivery": "best_effort"}, [f"*Reel* {args.action}: {text(fields.get('place') or fields['reason'])}"]
    store = Store()
    if args.group == "fx":
        data = money.convert(store, args.amount, args.source, args.target)
        return data, [f"*FX* {data['amount']} {data['from']} = {data['converted']} {data['to']}", *fx_lines(data["fx"])]
    return {"trip": trip_command, "wishlist": wishlist_command, "spend": spend_command,
            "budget": budget_command}[args.group](args, store)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv or argv[:2] == ["reel", "fetch"]
    argv = [arg for arg in argv if arg != "--json"]
    try:
        args = parser().parse_args(argv)
        data, lines = dispatch(args)
        result = {"ok": True, **data}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False) if as_json else "\n".join(lines))
        return 0 if result["ok"] else 1
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as exc:
        reason = text(exc)
        if isinstance(exc, OSError):
            reason = "Local file or lock operation failed; check state directory permissions and active writers."
        result = {"ok": False, "reason": reason}
        print(json.dumps(result, ensure_ascii=False) if as_json else f"*Error* {reason}")
        return 1
