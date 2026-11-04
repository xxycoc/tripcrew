"""One lock covers read/modify/write, including cross-file reference checks."""

import json
import os
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from filelock import FileLock


ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "trip": {
        "start": "2026-12-10", "end": "2026-12-16",
        "cities": ["Osaka", "Kyoto"], "budget_myr": "6000.00",
        "interests": [], "days": {},
    },
    "wishlist": [],
    "spend": [],
    "fx": {},
}


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("TRIPCREW_STATE") or ROOT / "state")
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.root / ".tripcrew.lock"), timeout=15)

    @contextmanager
    def transaction(self):
        with self.lock:
            yield self

    def read(self, name):
        path = self.root / f"{name}.json"
        if not path.exists():
            return deepcopy(DEFAULTS[name])
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, type(DEFAULTS[name])):
                raise ValueError("wrong top-level type")
            return value
        except (ValueError, OSError) as exc:
            raise ValueError(f"Cannot read {name}.json; fix its JSON before continuing.") from exc

    def write(self, name, value):
        # Same-directory replacement keeps readers on either the old or new complete file.
        fd, temporary = tempfile.mkstemp(prefix=f".{name}-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.root / f"{name}.json")
        finally:
            Path(temporary).unlink(missing_ok=True)
