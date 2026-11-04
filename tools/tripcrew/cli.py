import argparse
from datetime import date
from decimal import Decimal
import json
import sys
from urllib.parse import urlencode
from uuid import uuid4

from . import activity, money, receipts, reels
from .store import Store


DATES_REQUIRED = "Trip dates aren't set yet; use trip set --start YYYY-MM-DD --end YYYY-MM-DD."
TRIP_SETUP = ("Use trip set --start YYYY-MM-DD --end YYYY-MM-DD --cities CITY [CITY ...] "
              "--budget-sgd AMOUNT --interests INTEREST [INTEREST ...].")
MAP_WAYPOINT_LIMIT = 3  # URLs API limit for mobile browsers, excluding the two endpoints.


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
    mapping = commands.add_parser("map", help="Read Google Maps links for one day or every planned day.")
    mapping.add_argument("day", nargs="?", type=int, help="Trip day, starting at 1; omit for all planned days.")
    setting = commands.add_parser("set", help="Change only supplied settings; preserve itinerary.")
    setting.add_argument("--start", help="First date, YYYY-MM-DD (inclusive).")
    setting.add_argument("--end", help="Last date, YYYY-MM-DD (inclusive).")
    setting.add_argument("--cities", nargs="+", help="Replace cities; quote multiword names.")
    setting.add_argument("--budget-sgd", help="Total SGD budget, at most two decimal places.")
    setting.add_argument("--interests", nargs="+", help="Replace interests; quote multiword interests.")
    setting.add_argument("--categories", nargs="+", metavar="NAME=AMOUNT",
                         help="Replace SGD budget categories, e.g. flight=700 other=800; "
                              "amounts must add up to the total budget.")
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
    add.add_argument("--reel", action="store_true", help="Let the following reel identified command animate this place; skip the wishlist card.")
    listing = commands.add_parser("list", help="Filter saved places; --unplanned excludes all itinerary stops.")
    listing.add_argument("--city")
    listing.add_argument("--category", choices=["food", "attraction", "tip"])
    listing.add_argument("--unplanned", action="store_true")
    remove = commands.add_parser("remove", help="Remove a place after removing its itinerary references.")
    remove.add_argument("id")
    price = commands.add_parser("price", help="Budget: set or update an estimate with its source note.")
    price.add_argument("id")
    price.add_argument("--price-jpy", required=True, help="Estimated JPY amount; 0 is free, unknown clears it.")
    price.add_argument("--source-note", required=True, help="Short source and context for this estimate.")

    spend = groups.add_parser("spend", help="Record actual spending. JPY entries keep the original and FX used.")
    commands = spend.add_subparsers(dest="action", required=True)
    add = commands.add_parser("add", help="Record one expense; stores SGD value at entry time.")
    add.add_argument("amount")
    add.add_argument("currency", type=str.upper, choices=["JPY", "SGD"])
    add.add_argument("--note", required=True)
    add.add_argument("--day", type=int, help="Trip day; omit for spending before the trip, such as flights.")
    add.add_argument("--category", help="Budget category; required once categories are set.")
    add.add_argument("--receipt", help="Local receipt image to copy into state/receipts/ when recorded (max 10 MiB).")
    commands.add_parser("list", help="List expenses with original currency and booked SGD amounts.")

    budget = groups.add_parser("budget", help="Budget and actual spending in SGD; does not edit itinerary.")
    commands = budget.add_subparsers(dest="action", required=True)
    status = commands.add_parser("status", help="Total, per-category and daily budget/spent/left. Categories at 80%% or more are flagged.")
    status.add_argument("--day", type=int, help="Show only this day's detail, plus trip totals.")
    check = commands.add_parser("check", help="Read-only planned costs plus actual spending against non-flight daily allowance.")
    check.add_argument("--day", type=int, help="Check this day; omit for every day with planned stops.")

    fx = groups.add_parser("fx", help="Frankfurter JPY/SGD conversion; 12-hour cache, explicit stale fallback.")
    commands = fx.add_subparsers(dest="action", required=True)
    conversion = commands.add_parser("convert", help="Convert JPY or SGD; never substitutes an invented rate.")
    conversion.add_argument("amount")
    conversion.add_argument("source", type=str.upper, choices=["JPY", "SGD"])
    conversion.add_argument("target", type=str.upper, choices=["JPY", "SGD"])

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
    if not trip["start"] or not trip["end"]:
        raise ValueError(DATES_REQUIRED)
    count = (date.fromisoformat(trip["end"]) - date.fromisoformat(trip["start"])).days + 1
    if count <= 0:
        raise ValueError("Trip end must be on or after its start.")
    return count


def check_day(trip, day):
    count = day_count(trip)
    if not 1 <= day <= count:
        raise ValueError(f"Day must be between 1 and {count}.")


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
    return [f"*FX* 1 JPY = {fx['rate']} SGD; rate date {fx['date']}; "
            f"{fx['source']}, fetched {fx['age_seconds'] / 3600:.1f} hours ago."]


def wishlist_line(item):
    price = "price unknown" if item["price_jpy"] is None else f"JPY {item['price_jpy']} estimated"
    return (f"*{item['id']}* {text(item['name'])}, {text(item['area'])}, {text(item['city'])}; "
            f"{item['category']}; {price}; {'verified' if item['verified'] else 'unverified'}"
            + (f"; hours: {text(item['hours'])}" if item['hours'] else "")
            + (f"; {text(item['source_url'])}" if item['source_url'] else "")
            + (f"; price source: {text(item['price_source_note'])}" if item.get("price_source_note") else "")
            + (f"; {text(item['note'])}" if item['note'] else ""))


def spend_line(item):
    original = f" (JPY {item['amount']})" if item["currency"] == "JPY" else ""
    when = "Before trip" if item["day"] is None else f"Day {item['day']}"
    category = f" [{item['category']}]" if item.get("category") else ""
    return (f"*{item['id']}* {when}{category}: SGD {item['amount_sgd']}{original}; {text(item['note'])}"
            + (f"; receipt: {item['receipt']}" if item.get("receipt") else ""))


def parse_categories(values):
    categories = {}
    for value in values:
        name, separator, amount = value.partition("=")
        name = name.strip().casefold()
        if not separator or not name:
            raise ValueError("Categories must look like NAME=AMOUNT, e.g. flight=700.")
        if name in categories:
            raise ValueError(f"Category {name} is listed twice.")
        amount = money.number(amount)
        if money.cents(amount) != amount:
            raise ValueError("Category amounts must have at most two decimal places.")
        categories[name] = str(money.cents(amount))
    return categories


def map_days(trip, wishlist, day):
    count = day_count(trip)
    if day is not None:
        check_day(trip, day)
    days = [day] if day is not None else [n for n in range(1, count + 1) if trip["days"].get(str(n))]
    places = {item["id"]: item for item in wishlist}
    results, lines = [], []
    for number in days:
        stops = []
        for stop in trip["days"].get(str(number), []):
            if stop not in places:
                raise ValueError(f"Day {number} references missing wishlist ID {stop}; fix the itinerary first.")
            stops.append({key: places[stop][key] for key in ("id", "name", "area", "city")})
        used, dropped = stops[:MAP_WAYPOINT_LIMIT + 2], stops[MAP_WAYPOINT_LIMIT + 2:]
        result = {"day": number, "url": None, "stops": used, "dropped_stops": dropped}
        if not used:
            result["message"] = "Unplanned; no stops to map."
            lines.append(f"*Day {number}* {result['message']}")
        else:
            queries = [", ".join(text(stop[key]) for key in ("name", "area", "city")) for stop in used]
            if len(queries) == 1:
                action, params = "search", {"api": 1, "query": queries[0]}
            else:
                action, params = "dir", {"api": 1, "origin": queries[0], "destination": queries[-1]}
                if len(queries) > 2:
                    params["waypoints"] = "|".join(queries[1:-1])
                params["travelmode"] = "transit"
            result["url"] = f"https://www.google.com/maps/{action}/?{urlencode(params)}"
            if len(result["url"]) > 2048:
                raise ValueError(f"Day {number} map URL exceeds the URLs API's 2048-character limit; shorten place details.")
            warning = ""
            if dropped:
                warning = (f"Omitted {len(dropped)} later stop(s): mobile Maps URLs support at most "
                           f"{MAP_WAYPOINT_LIMIT} waypoints (5 stops).")
                result["warning"] = warning
            lines.append(f"*Day {number}* {result['url']}" + (f" ({warning})" if warning else ""))
        results.append(result)
    return {"days": results}, lines or ["*Map* No planned days yet; add stops with trip day N add WISHLIST_ID."]


def trip_command(args, store):
    with store.transaction():
        trip = store.read("trip")
        wishlist = store.read("wishlist")
        if args.action == "map":
            return map_days(trip, wishlist, args.day)
        if args.action == "set":
            supplied = [args.start, args.end, args.cities, args.budget_sgd, args.interests, args.categories]
            if all(value is None for value in supplied):
                raise ValueError("Supply at least one trip setting; see trip set --help.")
            for key in ("start", "end", "cities", "interests"):
                value = getattr(args, key)
                if value is not None:
                    if key in ("start", "end"):
                        date.fromisoformat(value)
                    if isinstance(value, list) and any(not part.strip() for part in value):
                        raise ValueError(f"{key} cannot contain empty values.")
                    trip[key] = value
            if trip["start"] and trip["end"]:
                count = day_count(trip)
                if any(int(day) > count and stops for day, stops in trip["days"].items()):
                    raise ValueError("New dates would discard planned days; remove or move those stops first.")
                if any(item["day"] > count for item in store.read("spend")):
                    raise ValueError("New dates would exclude recorded spending; keep those days in the trip.")
                trip["days"] = {day: stops for day, stops in trip["days"].items() if int(day) <= count}
            if args.budget_sgd is not None:
                amount = money.number(args.budget_sgd)
                if money.cents(amount) != amount:
                    raise ValueError("SGD budget must have at most two decimal places.")
                trip["budget_sgd"] = str(money.cents(amount))
            if args.categories is not None:
                trip["categories"] = parse_categories(args.categories)
            if trip.get("categories"):
                if trip["budget_sgd"] is None:
                    raise ValueError("Set the total with --budget-sgd before adding categories.")
                allotted = sum(Decimal(value) for value in trip["categories"].values())
                if allotted != Decimal(trip["budget_sgd"]):
                    raise ValueError(f"Categories add up to SGD {allotted}, but the budget is SGD "
                                     f"{trip['budget_sgd']}; make them match.")
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
    if args.action == "set":
        if any(value is not None for value in (args.start, args.end, args.cities)):
            dates = [date.fromisoformat(value) for value in (trip["start"], trip["end"]) if value]
            labels = [f"{value.day} {value:%b}" for value in dates]
            if len(dates) == 2 and dates[0].year != dates[1].year:
                labels = [f"{value.day} {value:%b %Y}" for value in dates]
            elif len(dates) == 2 and dates[0].month == dates[1].month:
                labels[0] = str(dates[0].day)
            summary = ", ".join(value for value in ("–".join(labels), " + ".join(trip["cities"])) if value)
            activity.post_event("planner", "you", "finalised", f"Trip: {summary}")
        if args.budget_sgd is not None or args.categories is not None:
            amount = format(Decimal(trip["budget_sgd"]), ",.2f").removesuffix(".00")
            activity.post_event("budget", "you", "finalised", f"Budget S${amount}")
    elif args.action == "day" and args.operation in {"add", "move"}:
        destination = getattr(args, "to_day", None)
        destination = args.day if destination is None else destination
        activity.post_event("planner", "you", "finalised", f"Day {destination}: {names[args.id]}")
    if not any(trip[key] for key in ("start", "end", "cities", "interests", "days")) and trip["budget_sgd"] is None:
        return {"trip": trip}, ["*Trip* No trip is set yet.", f"*Setup* {TRIP_SETUP}"]
    dates = f"{trip['start'] or 'not set'} to {trip['end'] or 'not set'}"
    lines = [f"*Trip* {dates}; {', '.join(map(text, trip['cities'])) or 'cities not set'}",
             f"*Interests* {', '.join(map(text, trip['interests'])) or 'not set'}"]
    if trip.get("categories"):
        lines.append("*Budget categories* " + ", ".join(trip["categories"]))
    if not trip["start"] or not trip["end"]:
        return {"trip": trip}, [*lines, f"*Setup* {DATES_REQUIRED}"]
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
            # Post outside the transaction so an offline relay does not hold the state lock.
        elif args.action == "price":
            if not args.source_note.strip():
                raise ValueError("Price source note cannot be blank.")
            item = next((entry for entry in entries if entry["id"] == args.id), None)
            if item is None:
                raise ValueError("Unknown wishlist ID.")
            item["price_jpy"] = (None if args.price_jpy.casefold() == "unknown"
                                 else str(money.number(args.price_jpy)))
            item["price_source_note"] = text(args.source_note)
            store.write("wishlist", entries)
        elif args.action == "remove":
            if args.id in planned:
                raise ValueError("Place is on the itinerary; remove its stops before removing the wishlist entry.")
            remaining = [entry for entry in entries if entry["id"] != args.id]
            if len(remaining) == len(entries):
                raise ValueError("Unknown wishlist ID.")
            store.write("wishlist", remaining)
            return {"removed": args.id}, [f"*Removed* {args.id}"]
        else:
            entries = [entry for entry in entries
                       if (not args.city or entry["city"].casefold() == args.city.casefold())
                       and (not args.category or entry["category"] == args.category)
                       and (not args.unplanned or entry["id"] not in planned)]
    if args.action == "add":
        if not args.reel:
            activity.post_event("reel_adder", "planner", "delegated", item["name"])
        return {"item": item}, [wishlist_line(item)]
    if args.action == "price":
        price = "price unknown" if item["price_jpy"] is None else f"¥{item['price_jpy']}"
        activity.post_event("budget", "planner", "finalised", f"{item['name']}: {price}")
        return {"item": item}, [wishlist_line(item)]
    return {"wishlist": entries}, [wishlist_line(item) for item in entries] or ["*Wishlist* empty"]


def spend_command(args, store):
    if args.action == "list":
        with store.transaction():
            entries = store.read("spend")
        return {"spend": entries}, [spend_line(item) for item in entries] or ["*Spend* no expenses"]
    amount = money.number(args.amount, positive=True)
    if args.currency == "SGD" and money.cents(amount) != amount:
        raise ValueError("SGD spending must have at most two decimal places.")
    if not args.note.strip():
        raise ValueError("Spend note cannot be blank.")
    category = args.category.strip().casefold() if args.category else None

    def check(trip):
        if args.day is not None:
            check_day(trip, args.day)
        categories = trip.get("categories") or {}
        if categories and category not in categories:
            raise ValueError("Pick a budget category with --category: " + ", ".join(categories) + ".")
        if not categories and category:
            raise ValueError("No budget categories are set; omit --category or set them with trip set --categories.")

    with store.transaction():
        check(store.read("trip"))
    receipt = receipts.load(args.receipt) if args.receipt else None
    conversion = money.convert(store, amount, args.currency, "SGD")
    with store.transaction():
        check(store.read("trip"))
        entries = store.read("spend")
        item = {"id": new_id("s_", entries), "amount": str(amount), "currency": args.currency,
                "amount_sgd": conversion["converted"], "note": args.note, "day": args.day, "category": category,
                "fx": conversion["fx"], "created_at": money.timestamp().isoformat()}
        entries.append(item)
        saved = None
        try:
            if receipt:
                saved = receipts.save(store, item["id"], receipt)
                item["receipt"] = saved.relative_to(store.root).as_posix()
            store.write("spend", entries)
        except Exception:
            if saved is not None:
                saved.unlink(missing_ok=True)
            raise
    activity.post_event("budget", "you", "finalised", f"S${item['amount_sgd']} · {item['note']}")
    return {"item": item}, [spend_line(item), *fx_lines(item["fx"])]


def budget_command(args, store):
    with store.transaction():
        trip, entries = store.read("trip"), store.read("spend")
        wishlist = store.read("wishlist") if args.action == "check" else []
    missing = []
    if trip["budget_sgd"] is None:
        missing.append("Budget isn't set yet; use trip set --budget-sgd AMOUNT.")
    if not trip["start"] or not trip["end"]:
        missing.append(DATES_REQUIRED)
    if missing:
        raise ValueError(" ".join(missing))
    count = day_count(trip)
    if args.day is not None:
        check_day(trip, args.day)
    total_budget = money.cents(money.number(trip["budget_sgd"]))
    if args.action == "check":
        return day_cost_check(args, store, trip, entries, wishlist, count, total_budget)
    total_spent = sum((Decimal(item["amount_sgd"]) for item in entries), Decimal("0.00"))
    totals = {"budget_sgd": str(total_budget), "spent_sgd": str(total_spent),
              "left_sgd": str(total_budget - total_spent)}
    base, extra = divmod(int(total_budget * 100), count)
    days = []
    for day in range(1, count + 1):
        day_budget = Decimal(base + (day <= extra)) / 100
        expenses = [item for item in entries if item["day"] == day]
        spent = sum((Decimal(item["amount_sgd"]) for item in expenses), Decimal("0.00"))
        days.append({"day": day, "budget_sgd": str(money.cents(day_budget)), "spent_sgd": str(spent),
                     "left_sgd": str(money.cents(day_budget - spent)), "spend": expenses})
    selected = [day for day in days if args.day is None or day["day"] == args.day]
    categories = []
    for name, value in (trip.get("categories") or {}).items():
        allotted = Decimal(value)
        spent = sum((Decimal(item["amount_sgd"]) for item in entries if item.get("category") == name),
                    Decimal("0.00"))
        used = int(spent * 100 / allotted) if allotted else (100 if spent else 0)
        categories.append({"category": name, "budget_sgd": str(allotted), "spent_sgd": str(spent),
                           "left_sgd": str(allotted - spent), "used_percent": used, "warning": used >= 80})
    lines = [f"*Total* SGD {totals['budget_sgd']} budget; {totals['spent_sgd']} spent; {totals['left_sgd']} left"]
    for item in categories:
        lines.append(f"*{item['category'].capitalize()}* SGD {item['budget_sgd']} budget; {item['spent_sgd']} spent; "
                     f"{item['left_sgd']} left ({item['used_percent']}% used"
                     + (", over 80%)" if item["warning"] else ")"))
    for day in selected:
        originals = [f"JPY {item['amount']} → SGD {item['amount_sgd']}" for item in day["spend"]
                     if item["currency"] == "JPY"]
        # An even daily split of the total would count the flight against each day.
        summary = (f"SGD {day['spent_sgd']} spent" if categories else
                   f"SGD {day['budget_sgd']} budget; {day['spent_sgd']} spent; {day['left_sgd']} left")
        lines.append(f"*Day {day['day']}* {summary}" + (f" ({'; '.join(originals)})" if originals else ""))
    return {"totals": totals, "categories": categories, "days": selected}, lines


def day_cost_check(args, store, trip, entries, wishlist, count, total_budget):
    categories = trip.get("categories") or {}
    allowance = (sum((Decimal(value) for name, value in categories.items() if name != "flight"),
                     Decimal("0.00")) if categories else total_budget)
    base, extra = divmod(int(allowance * 100), count)
    selected = [args.day] if args.day is not None else [
        day for day in range(1, count + 1) if trip["days"].get(str(day))]
    places = {item["id"]: item for item in wishlist}
    planned = {day: [places[stop] for stop in trip["days"].get(str(day), [])] for day in selected}
    known_jpy = sum((Decimal(item["price_jpy"]) for stops in planned.values() for item in stops
                     if item["price_jpy"] is not None), Decimal("0"))
    # Resolve FX once so all days and ranked stops use the same rate, including offline fallback.
    fx = money.convert(store, known_jpy, "JPY", "SGD")["fx"] if known_jpy else None
    factor = Decimal(fx["rate"]) if fx else Decimal("0")
    days, lines = [], []
    for day, stops in planned.items():
        known = [item for item in stops if item["price_jpy"] is not None]
        unknown = [{"id": item["id"], "name": item["name"]} for item in stops if item["price_jpy"] is None]
        estimate_jpy = sum((Decimal(item["price_jpy"]) for item in known), Decimal("0"))
        estimate = money.cents(estimate_jpy * factor)
        actual = sum((Decimal(item["amount_sgd"]) for item in entries if item["day"] == day), Decimal("0.00"))
        allotted = money.cents(Decimal(base + (day <= extra)) / 100)
        total = estimate + actual
        difference = total - allotted
        status = "over" if difference > 0 else "under" if difference < 0 else "at_allowance"
        expensive = [{"id": item["id"], "name": item["name"], "area": item["area"], "city": item["city"],
                      "price_jpy": item["price_jpy"],
                      "estimate_sgd": str(money.cents(Decimal(item["price_jpy"]) * factor))}
                     for item in sorted(known, key=lambda item: Decimal(item["price_jpy"]), reverse=True)[:3]]
        days.append({"day": day, "estimate_jpy": str(estimate_jpy), "estimate_sgd": str(estimate),
                     "actual_sgd": str(actual), "total_sgd": str(total), "allowance_sgd": str(allotted),
                     "difference_sgd": str(difference), "status": status, "over_budget": difference > 0,
                     "unknown_count": len(unknown), "unknown_stops": unknown, "complete": not unknown,
                     "most_expensive_stops": expensive})
        flag = f"{status.upper()} by SGD {abs(difference)}" if difference else "AT ALLOWANCE"
        lines.append(f"*Day {day}* {flag}; SGD {estimate} estimated + {actual} actual = {total}; "
                     f"allowance {allotted}; {len(unknown)} unknown price(s)"
                     + ("; minimum known cost only" if unknown else ""))
        if expensive:
            lines.append("*Most expensive* " + "; ".join(
                f"{item['id']} {text(item['name'])}, {text(item['area'])}: SGD {item['estimate_sgd']} estimated"
                for item in expensive))
    return {"days": days, "fx": fx}, [*(lines or ["*Check* No planned days."]), *fx_lines(fx)]


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
