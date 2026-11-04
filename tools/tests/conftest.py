import pytest


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("TRIPCREW_STATE", str(tmp_path / "state"))
    monkeypatch.delenv("TRIPCREW_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.delenv("TRIPCREW_WHISPER_MODEL", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("Unexpected network request"))
    monkeypatch.setattr("tripcrew.money.urlopen", lambda *a, **k: pytest.fail("Unexpected FX request"))
    monkeypatch.setattr("tripcrew.reels.urlopen", lambda *a, **k: pytest.fail("Unexpected relay request"))


@pytest.fixture
def call(capsys):
    from tripcrew.cli import main

    def run(*args, ok=True):
        import json

        code = main([*args, "--json"])
        output = capsys.readouterr()
        assert not output.err
        data = json.loads(output.out)
        assert data["ok"] is ok, data
        assert code == (0 if ok else 1)
        return data

    return run


@pytest.fixture
def demo_trip(call):
    return call("trip", "set", "--start", "2026-12-10", "--end", "2026-12-16",
                "--cities", "Osaka", "Kyoto", "--budget-sgd", "6000")["trip"]
