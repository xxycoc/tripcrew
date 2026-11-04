# TripCrew CLI

Python 3.12+, managed by uv. The project has `package = false`: uv runs the
module directly and never builds this project. Install project dependencies with
`uv sync --project tools --group dev` from the repository root.

Run `bin/tripcrew ...` on sh, or `bin\tripcrew.cmd ...` on Windows. Both resolve
the project from their own location, so `../../bin/tripcrew` (Windows:
`..\..\bin\tripcrew.cmd`) works inside any `agents/<name>/` directory. You can
also run `uv run --directory tools python -m tripcrew ...` from the repo root.

Default output uses short Telegram Markdown lines with `*labels*`, without
tables. Put `--json` anywhere for JSON. `reel fetch` always prints JSON, including
failures. Success exits 0, failure exits 1; `--help` exits 0.

## Commands

```text
trip show
trip set [--start YYYY-MM-DD] [--end YYYY-MM-DD]
         [--cities Osaka Kyoto] [--budget-myr 6000] [--interests food temples]
trip day N add WISHLIST_ID [--position N]
trip day N remove WISHLIST_ID
trip day N move WISHLIST_ID [--position N] [--to-day N]

wishlist add --name NAME --area AREA --city CITY
             --category food|attraction|tip [--price-jpy AMOUNT]
             [--hours HOURS] [--url SOURCE_URL] [--verified] [--note NOTE]
wishlist list [--city CITY] [--category food|attraction|tip] [--unplanned]
wishlist remove WISHLIST_ID

spend add AMOUNT JPY|MYR --note NOTE --day N
spend list
budget status [--day N]
fx convert AMOUNT JPY|MYR JPY|MYR

reel fetch URL [--audio]
reel identified --place "Name, area" [--platform tiktok|instagram]
reel failed --reason REASON [--platform tiktok|instagram]
```

Planner owns itinerary edits and should use `trip show`, which omits prices in
human output. Budget owns spending and prices and does not need to edit the
itinerary. Reel Adder reads extraction JSON, verifies a place independently by
web search, adds its sourced wishlist entry and then posts `reel identified`.
The CLI does not pretend that metadata or a machine transcript verifies a place.

Days and positions start at 1. A move's position is the final position after
removal; omit it to append. Stops contain wishlist IDs in order. A wishlist entry
cannot be removed while it is on the itinerary. Changes to dates cannot exclude
planned stops or existing expenses. Omitted settings are preserved. Dates are
inclusive, with the demo default of 10–16 December 2026, Osaka/Kyoto, MYR 6,000.

`wishlist add` leaves price unknown when `--price-jpy` is omitted; zero means
free. Entries start unverified unless the agent explicitly supplies `--verified`.

## State and money

State defaults to the repository's `state/` directory, independent of the caller's
working directory. Set `TRIPCREW_STATE` to an alternate directory. Prefer an
absolute path; relative paths resolve against `tools/` when using the launchers.
Missing JSON files use defaults until their first mutation. The four files are:

- `trip.json`: settings and `days`, an object mapping day numbers to ordered IDs.
- `wishlist.json`: place objects with stable `w_` IDs.
- `spend.json`: expense objects with stable `s_` IDs and original currency.
- `fx.json`: the last successfully fetched JPY-to-MYR rate and its timestamps.

One `filelock` lock covers complete read/modify/write operations, including
wishlist reference checks. Writes use a flushed and fsynced temporary file in
the same directory followed by atomic replacement. Readers use the same lock
(also avoiding Windows replacement conflicts with open read handles). JSON is
indented UTF-8; stop writers before hand-editing it. Malformed JSON is reported
and preserved rather than overwritten.

Money uses Decimal, with MYR amounts rounded half up to cents. Spending preserves
the original amount and the MYR amount booked using that entry's FX, so a later
rate refresh does not rewrite history. Daily budget shares sum exactly to the
trip budget; extra cents go to the earliest days. Negative amounts left indicate
overspending. `budget status --day` keeps trip totals and filters daily detail.

[Frankfurter's documented v1 endpoint](https://frankfurter.dev/v1/) is
`https://api.frankfurter.dev/v1/latest?base=JPY&symbols=MYR`. v1 is deprecated but
continues to work. Cache lifetime is 12 hours from fetch time, distinct from the
published rate date. An expired cache is refreshed; when offline, the old rate is
used with an explicit age warning. With no usable cache, conversion fails.
Same-currency conversion and MYR spending need no network.

## Reels and relay

Metadata comes from yt-dlp's Python API with video download disabled. It includes
title, description/caption, hashtags, uploader, duration and available location.
Captions with fewer than eight words of at least two characters (excluding URLs,
hashtags and mentions) trigger audio transcription, as does `--audio`.

Audio uses strictly `bestaudio`, never a video fallback. If the platform supplies
no separate audio stream, fetching returns `ok: false` with its reason and any
metadata already extracted. Temporary audio is removed on success or failure.
faster-whisper uses CPU/int8 and model `small`, overridden with
`TRIPCREW_WHISPER_MODEL`. Its first use may download model weights. PyAV handles
the downloaded audio without an external ffmpeg conversion step.
PyAV is constrained below 19 because the released faster-whisper 1.2.1 still
passes the removed `metadata_errors` argument. A real decoder test guards this
[upstream compatibility issue](https://github.com/SYSTRAN/faster-whisper/issues/1492).

`TRIPCREW_COOKIES_FROM_BROWSER` accepts yt-dlp's browser syntax, such as `firefox`
or `firefox:profile::container`. It is passed to both metadata and audio requests.
Cookies are read only when explicitly configured; none are saved to state.

Events follow [the relay contract](../docs/events.md): `POST /reel` with `type`,
`step` and available fields, without `v` or `ts`. The watching event carries a
160-character caption snippet in `caption`. `TRIPCREW_RELAY_URL` defaults to
`http://127.0.0.1:8771`. Each request has a one-second timeout; failure is silent.
The CLI's explicit event commands report best-effort submission, not delivery.
Fetch failures never post `failed`; that decision belongs to the agent.

## Tests

From the repo root:

```sh
uv run --directory tools python -m pytest -q
```

Tests block unintended network requests and mock Frankfurter, yt-dlp, Whisper
and relay calls. They include process-level writer contention, failed atomic
replacement, money rounding and historical rates, cache expiry/offline fallback,
itinerary references, reel extraction/transcription cleanup and actual module
and launcher subprocesses. A separate live check is recorded in `result.md`.

If the machine's default uv cache is inaccessible, set `UV_CACHE_DIR` to a
writable local directory such as `.uv-cache` before running uv. This does not
change machine configuration and the local cache is gitignored.
