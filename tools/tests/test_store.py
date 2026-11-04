from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
from pathlib import Path

from filelock import FileLock, Timeout
import pytest

from tripcrew.store import Store


def increment(root, times):
    store = Store(root)
    for _ in range(times):
        with store.transaction():
            entries = store.read("spend")
            entries.append({"n": len(entries)})
            store.write("spend", entries)


def test_lock_prevents_lost_updates_between_processes(tmp_path):
    context = multiprocessing.get_context("spawn")
    workers = [context.Process(target=increment, args=(str(tmp_path), 15)) for _ in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
        if worker.is_alive():
            worker.terminate()
            worker.join()
            pytest.fail("Writer did not finish")
        assert worker.exitcode == 0
    assert Store(tmp_path).read("spend") == [{"n": n} for n in range(45)]


def test_lock_is_held_during_transaction(tmp_path):
    store = Store(tmp_path)
    with store.transaction():
        with pytest.raises(Timeout):
            with FileLock(str(tmp_path / ".tripcrew.lock"), timeout=0):
                pytest.fail("Competing writer acquired the lock")


def test_atomic_replace_failure_leaves_original_and_cleans_temp(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.write("wishlist", [{"name": "大阪"}])
    before = (tmp_path / "wishlist.json").read_bytes()

    def fail_replace(source, destination):
        assert Path(source).parent == Path(destination).parent == tmp_path
        assert json.loads(Path(source).read_text(encoding="utf-8")) == [{"name": "new"}]
        raise OSError("simulated interruption")

    monkeypatch.setattr("tripcrew.store.os.replace", fail_replace)
    with pytest.raises(OSError):
        store.write("wishlist", [{"name": "new"}])
    assert (tmp_path / "wishlist.json").read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_locked_readers_never_see_partial_json(tmp_path):
    store = Store(tmp_path)
    store.write("wishlist", [])

    def write():
        for n in range(25):
            with store.transaction():
                store.write("wishlist", [{"n": n, "text": "京都" * 1000}])

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(write)
        while not writer.done():
            with store.transaction():
                assert isinstance(json.loads((tmp_path / "wishlist.json").read_text(encoding="utf-8")), list)
        writer.result()


def test_corrupt_state_is_not_overwritten(tmp_path):
    (tmp_path / "trip.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot read trip.json"):
        Store(tmp_path).read("trip")
    assert (tmp_path / "trip.json").read_text(encoding="utf-8") == "{broken"


def test_defaults_are_independent(tmp_path):
    store = Store(tmp_path)
    first = store.read("trip")
    first["cities"].append("Tokyo")
    first["interests"].append("food")
    first["days"]["1"] = ["w_example"]
    assert store.read("trip") == {
        "start": None, "end": None, "cities": [], "budget_myr": None, "interests": [], "days": {}}
