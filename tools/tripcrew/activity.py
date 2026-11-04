import json
import os
from urllib.request import Request, urlopen


def post_event(from_actor, to_actor, state, summary):
    """Submit one task card, best effort; a relay failure never fails the write."""
    payload = {"type": "task", "from": from_actor, "to": to_actor, "state": state,
               "summary": " ".join(summary.split())[:80]}
    try:
        url = os.environ.get("TRIPCREW_RELAY_URL", "http://127.0.0.1:8771").rstrip("/") + "/activity"
        request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=1):
            pass
    except Exception:
        pass
    return payload
