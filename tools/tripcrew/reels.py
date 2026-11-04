import os
from optparse import OptParseError
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import json
from contextlib import redirect_stderr
from io import StringIO


class QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def post_event(step, **fields):
    payload = {"type": "reel", "step": step, **{k: v for k, v in fields.items() if v is not None}}
    try:
        url = os.environ.get("TRIPCREW_RELAY_URL", "http://127.0.0.1:8771").rstrip("/") + "/reel"
        request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=1):
            pass
    except Exception:
        pass
    return payload


def platform_for(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("Use a public TikTok or Instagram HTTP(S) URL.")
    host = (parsed.hostname or "").lower()
    for platform, domain in (("tiktok", "tiktok.com"), ("instagram", "instagram.com")):
        if host == domain or host.endswith("." + domain):
            return platform
    raise ValueError("Unsupported platform; use a TikTok or Instagram URL.")


def options():
    import yt_dlp

    result = {"quiet": True, "no_warnings": True, "logger": QuietLogger(),
              "noplaylist": True, "socket_timeout": 15, "retries": 1,
              "extractor_retries": 1}
    cookies = os.environ.get("TRIPCREW_COOKIES_FROM_BROWSER")
    if cookies:
        # Use yt-dlp's own parser for browser[:profile][::container] and keyring syntax.
        try:
            with redirect_stderr(StringIO()):
                result["cookiesfrombrowser"] = yt_dlp.parse_options(
                    ["--ignore-config", "--cookies-from-browser", cookies]
                ).ydl_opts["cookiesfrombrowser"]
        except (SystemExit, OptParseError, ValueError) as exc:
            raise ValueError("Invalid TRIPCREW_COOKIES_FROM_BROWSER; use yt-dlp browser[:profile][::container] syntax.") from exc
    return result


def meaningful_words(caption):
    text = re.sub(r"https?://\S+|[#@]\S+", "", caption)
    return [word for word in re.findall(r"[^\W_]+", text, flags=re.UNICODE) if len(word) > 1]


def transcribe(url, opts):
    import yt_dlp
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory(prefix="tripcrew-audio-") as folder:
        audio_opts = {**opts, "format": "bestaudio", "skip_download": False,
                      "outtmpl": str(Path(folder) / "audio.%(ext)s")}
        with yt_dlp.YoutubeDL(audio_opts) as downloader:
            info = downloader.extract_info(url, download=True)
            audio_path = Path(downloader.prepare_filename(info))
        if not audio_path.is_file() or not audio_path.resolve().is_relative_to(Path(folder).resolve()):
            raise ValueError("Audio download did not produce a temporary audio file.")
        model = WhisperModel(os.environ.get("TRIPCREW_WHISPER_MODEL", "small"),
                             device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments).strip()


def fetch(url, audio=False):
    platform = None
    result = {"ok": False, "url": url}
    try:
        import yt_dlp

        platform = platform_for(url)
        result["platform"] = platform
        post_event("fetch_start", platform=platform)
        opts = options()
        with yt_dlp.YoutubeDL({**opts, "skip_download": True}) as downloader:
            info = downloader.extract_info(url, download=False)
        if not isinstance(info, dict) or info.get("_type") in {"playlist", "multi_video"}:
            raise ValueError("Expected one video; use its individual reel URL.")
        caption = info.get("description") or ""
        tags = list(dict.fromkeys([*(info.get("tags") or []), *re.findall(r"#([^\W#]+)", caption)]))
        result.update({"title": info.get("title"), "caption": caption, "description": caption,
                       "hashtags": tags, "uploader": info.get("uploader"),
                       "duration": info.get("duration"), "location": info.get("location")})
        post_event("watching", platform=platform, caption=" ".join(caption.split())[:160])
        if audio or len(meaningful_words(caption)) < 8:
            result["transcript"] = transcribe(url, opts)
        result["ok"] = True
    except Exception as exc:
        # The agent, not the extractor, decides whether to ask the traveller or give up.
        reason = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).strip()
        result["reason"] = reason or type(exc).__name__
    return result
