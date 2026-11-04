from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yt_dlp

from tripcrew import reels


CAPTION = "Discover this lovely ramen shop near Osaka station for dinner tonight #Osaka #ramen"


@pytest.fixture
def fake(monkeypatch):
    state = SimpleNamespace(events=[], calls=[], downloads=[], fail=None,
                            info={"title": "Dinner in Osaka", "description": CAPTION,
                                  "tags": ["Osaka"], "uploader": "travel_demo", "duration": 32.5,
                                  "location": "Osaka"})

    class Downloader(yt_dlp.YoutubeDL):
        def __init__(self, opts):
            self.opts = opts
            state.calls.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            if state.fail:
                raise ValueError(state.fail)
            if download:
                assert self.opts["format"] == "bestaudio"
                assert self.opts["skip_download"] is False
                path = self.prepare_filename(state.info)
                Path(path).write_bytes(b"mock audio")
                state.downloads.append(path)
            else:
                assert self.opts["skip_download"] is True
            return dict(state.info)

        def prepare_filename(self, info):
            return self.opts["outtmpl"].replace("%(ext)s", "m4a")

    class Whisper:
        def __init__(self, model, **kwargs):
            state.whisper = (model, kwargs)

        def transcribe(self, path):
            assert Path(path).exists()
            if getattr(state, "whisper_fail", False):
                raise RuntimeError("transcription unavailable")
            return iter([SimpleNamespace(text=" Visit "), SimpleNamespace(text=" Osaka station. ")]), None

    monkeypatch.setattr(yt_dlp, "YoutubeDL", Downloader)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Whisper))
    monkeypatch.setattr(reels, "post_event", lambda step, **fields: state.events.append({"step": step, **fields}))
    return state


@pytest.mark.parametrize("url,platform", [("https://www.tiktok.com/@demo/video/123", "tiktok"),
                                          ("https://www.instagram.com/reel/abc/", "instagram"),
                                          ("https://vm.tiktok.com/abc/", "tiktok")])
def test_metadata_json_and_events(call, fake, url, platform):
    result = call("reel", "fetch", url)
    assert result["platform"] == platform
    assert result["title"] == "Dinner in Osaka"
    assert result["caption"] == result["description"] == CAPTION
    assert result["hashtags"] == ["Osaka", "ramen"]
    assert result["location"] == "Osaka"
    assert result["duration"] == 32.5
    assert "transcript" not in result
    assert not fake.downloads
    assert fake.events == [{"step": "fetch_start", "platform": platform},
                           {"step": "watching", "platform": platform, "caption": CAPTION}]


@pytest.mark.parametrize("forced,short", [(True, False), (False, True)])
def test_audio_forced_or_automatic_and_cleaned(call, fake, monkeypatch, forced, short):
    if short:
        fake.info["description"] = "Wow! #osaka #japan #travel #food #ramen #yum #holiday #visit"
    monkeypatch.setenv("TRIPCREW_WHISPER_MODEL", "tiny")
    result = call("reel", "fetch", "https://www.instagram.com/reel/abc/", *(["--audio"] if forced else []))
    assert result["transcript"] == "Visit Osaka station."
    assert fake.whisper == ("tiny", {"device": "cpu", "compute_type": "int8"})
    assert len(fake.downloads) == 1
    assert not Path(fake.downloads[0]).parent.exists()


def test_default_whisper_model_and_failure_cleanup(call, fake):
    fake.whisper_fail = True
    result = call("reel", "fetch", "https://www.tiktok.com/@demo/video/123", "--audio", ok=False)
    assert result["reason"] == "transcription unavailable"
    assert result["title"] == "Dinner in Osaka"
    assert fake.whisper[0] == "small"
    assert not Path(fake.downloads[0]).parent.exists()
    assert [event["step"] for event in fake.events] == ["fetch_start", "watching"]


def test_extraction_failure_is_json_and_does_not_post_failed(call, fake):
    fake.fail = "TikTok refused access; try a public link."
    result = call("reel", "fetch", "https://www.tiktok.com/@demo/video/123", ok=False)
    assert result["reason"] == fake.fail
    assert fake.events == [{"step": "fetch_start", "platform": "tiktok"}]


@pytest.mark.parametrize("url", ["https://youtube.com/watch?v=a", "https://tiktok.com.evil.test/a",
                                "file:///tiktok.com/a", "https://user:pass@tiktok.com/a"])
def test_unsupported_url_is_json_without_events(call, fake, url):
    call("reel", "fetch", url, ok=False)
    assert not fake.events
    assert not fake.calls


def test_fetch_default_output_is_json(fake, capsys):
    from tripcrew.cli import main

    assert main(["reel", "fetch", "https://www.tiktok.com/@demo/video/123"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cookies_use_yt_dlp_syntax(call, fake, monkeypatch):
    monkeypatch.setenv("TRIPCREW_COOKIES_FROM_BROWSER", "firefox:demo-profile::Travel")
    call("reel", "fetch", "https://www.instagram.com/reel/abc/", "--audio")
    assert all(opts["cookiesfrombrowser"] == ("firefox", "demo-profile", None, "Travel") for opts in fake.calls)


def test_invalid_cookie_configuration_still_returns_json(call, fake, monkeypatch):
    monkeypatch.setenv("TRIPCREW_COOKIES_FROM_BROWSER", "nonexistent-browser")
    result = call("reel", "fetch", "https://www.instagram.com/reel/abc/", ok=False)
    assert "Invalid TRIPCREW_COOKIES_FROM_BROWSER" in result["reason"]


def test_single_video_required(call, fake):
    fake.info["_type"] = "playlist"
    result = call("reel", "fetch", "https://www.tiktok.com/@demo/video/123", ok=False)
    assert "individual reel" in result["reason"]


def test_post_event_contract_timeout_and_silent_offline(monkeypatch, capsys):
    requests = []

    def relay(request, timeout):
        requests.append((request, timeout))
        return BytesIO()

    monkeypatch.setenv("TRIPCREW_RELAY_URL", "http://relay.test:8771/")
    monkeypatch.setattr(reels, "urlopen", relay)
    reels.post_event("identified", platform="tiktok", place="Ramen, Umeda")
    request, timeout = requests[0]
    assert request.full_url == "http://relay.test:8771/reel"
    assert request.get_method() == "POST"
    assert timeout == 1
    assert json.loads(request.data) == {"type": "reel", "step": "identified", "platform": "tiktok", "place": "Ramen, Umeda"}

    def offline(*a, **k):
        raise OSError("relay absent")

    monkeypatch.setattr(reels, "urlopen", offline)
    reels.post_event("failed", reason="Could not verify")
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_identified_and_failed_are_explicit_events(call, fake):
    identified = call("reel", "identified", "--place", "Ramen, Umeda", "--platform", "tiktok")
    failed = call("reel", "failed", "--reason", "Could not verify")
    assert identified["delivery"] == failed["delivery"] == "best_effort"
    assert fake.events == [{"step": "identified", "platform": "tiktok", "place": "Ramen, Umeda"},
                           {"step": "failed", "platform": None, "reason": "Could not verify"}]
