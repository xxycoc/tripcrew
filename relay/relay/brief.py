from datetime import date
import json
import os
from pathlib import Path


BRIEF_TEXT = "@planner @budget Morning brief for {day} ({today}): please share today's plan and money left, each per your instructions."
REPO = Path(__file__).resolve().parents[2]


def morning_brief(state: Path | None = None, today: date | None = None) -> str:
    today = today or date.today()
    path = (state if state is not None else Path(os.environ.get("TRIPCREW_STATE", REPO / "state"))) / "trip.json"
    trip = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(trip, dict):
        raise ValueError("trip.json must contain a trip object")
    start, end = trip.get("start"), trip.get("end")
    day = "a test brief"
    if start and end:
        try:
            start, end = date.fromisoformat(start), date.fromisoformat(end)
        except (ValueError, TypeError) as exc:
            raise ValueError("trip.json start and end must be ISO dates (YYYY-MM-DD)") from exc
        if end < start:
            raise ValueError("trip.json end must be on or after start")
        if start <= today <= end:
            day = f"trip day {(today - start).days + 1}"
    return BRIEF_TEXT.format(day=day, today=today.isoformat())
