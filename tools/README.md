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
trip map [N]
trip set [--start YYYY-MM-DD] [--end YYYY-MM-DD]
         [--cities Osaka Kyoto] [--budget-sgd 1500] [--interests food temples]
         [--categories flight=700 other=800] [--people NAME ...]
trip day N add WISHLIST_ID [--position N]
trip day N remove WISHLIST_ID
trip day N move WISHLIST_ID [--position N] [--to-day N]

wishlist add --name NAME --area AREA --city CITY
             --category food|attraction|tip [--price-jpy AMOUNT]
             [--hours HOURS] [--url SOURCE_URL] [--verified] [--note NOTE] [--reel]
wishlist list [--city CITY] [--category food|attraction|tip] [--unplanned]
wishlist remove WISHLIST_ID
wishlist price WISHLIST_ID --price-jpy AMOUNT|unknown --source-note NOTE

spend add AMOUNT JPY|SGD --note NOTE [--day N] [--category NAME] [--receipt PATH]
          [--paid-by NAME] [--split NAME ...]
spend list
spend balances
budget status [--day N]
budget check [--day N]
fx convert AMOUNT JPY|SGD JPY|SGD
transcribe PATH [--language CODE]

reel fetch URL [--audio]
reel identified --place "Name, area" [--platform tiktok|instagram]
reel failed --reason REASON [--platform tiktok|instagram]
```

Planner owns itinerary edits and should use `trip show`, which omits prices in
human output. Budget owns spending and prices and does not need to edit the
itinerary. Reel Adder reads extraction JSON, verifies a place independently by
web search, adds its sourced wishlist entry and then posts `reel identified`.
For that sequence pass `wishlist add --reel` so only `reel identified` animates
the place. An ordinary wishlist addition sends its own Reel Adder → Planner card.
The CLI does not pretend that metadata or a machine transcript verifies a place.

Days and positions start at 1. A move's position is the final position after
removal; omit it to append. Stops contain wishlist IDs in order. A wishlist entry
cannot be removed while it is on the itinerary. Changes to dates cannot exclude
planned stops or existing expenses. Omitted settings are preserved. Dates are
inclusive. A fresh state has no trip: dates and budget are `null`, cities and
interests are empty lists, and days are an empty object. No destination, dates or
budget are assumed. Planner sets the dates, cities and interests from the
person's Telegram messages; Budget sets the requested budget. The Osaka/Kyoto
values above are examples to supply explicitly, not defaults.

`trip map N` reads one day's Google Maps link; `trip map` reads every planned day
in numeric day order, skipping unplanned days. Both require trip dates. Human
output is one `*Day N* <url>` line per planned day. An explicitly requested empty
day reports `Unplanned; no stops to map.`; no planned days produces a clear
message. The command makes no network requests or changes to saved state.

Links use the [Google Maps URLs API](https://developers.google.com/maps/documentation/urls/guide):
one stop opens search; two or more open directions with `travelmode=transit`.
Each query combines the stop's name, area and city in itinerary order, with
UTF-8 URL encoding. Source URLs, including Google Maps place links, are not parsed.
Mobile browsers support three intermediate waypoints (other platforms up to nine),
so links use the first five stops, ending at the fifth when a day is longer.
Later stops are omitted with an explicit warning. JSON returns `days` with
`day`, `url`, `stops` used (`id`, `name`, `area`, `city`), `dropped_stops` and any
`warning` or unplanned `message`; empty days have `url: null`. Links exceeding
the API's 2,048-character limit fail with a clear error. Maps products may ignore
waypoints when unsupported; phone routing and place matches require live review.

`trip show` explains that no trip is set yet and lists the `trip set` flags.
Settings can be supplied together or incrementally, including one date at a
time. Both dates are required before `trip day` or `spend add --day N` can proceed.
Omit `--day` to record pre-trip spending without dates.
`budget status`, including `--day`, requires both dates and a budget and explains
which settings are missing instead of calculating assumed amounts. A zero
budget is valid. Blocked actions exit 1; `--json` returns `ok: false` with a
`reason`. Reading an empty or partially configured trip succeeds with `ok: true`
and the current fields. Wishlist, reel and FX commands do not require a trip.

`wishlist add` leaves price unknown when `--price-jpy` is omitted; zero means
free. Entries start unverified unless the agent explicitly supplies `--verified`.
Budget can later set or update an estimate with `wishlist price ID --price-jpy
AMOUNT --source-note "Official menu; lunch set"`. The required source note is
stored as `price_source_note`, separately from the place note and source URL.
Use `--price-jpy unknown` to clear an outdated estimate; it never becomes free.

### Day cost check

`budget check --day N` reads that day's planned stops, including an empty day.
Without `--day`, it checks only days with planned stops. It requires both trip
dates and the budget, like `budget status`. It never changes the trip, wishlist
or spending; normal FX cache refreshes may update `fx.json`.

The allowance is the sum of all categories except `flight`, split across every
trip day. With no categories it uses the total budget. Remainder cents go to the
earliest days, so allowances sum exactly to the available budget. It converts
the day's known JPY estimates to SGD, rounds the day sum once, and adds actual
SGD spending already booked for that day. Pre-trip expenses have no day and are
excluded. All day-tagged spending counts, regardless of category. Actuals keep
their historical FX. Planned estimates are added in full; there is no matching
of receipts to itinerary stops, so an already-paid planned stop can count twice.

JSON returns `days` and `fx`. Each day includes `estimate_jpy`, `estimate_sgd`,
`actual_sgd`, `total_sgd`, `allowance_sgd`, and `difference_sgd` (total minus
allowance: positive is over, negative is under), `status` (`over`, `under`, or
`at_allowance`), and the boolean `over_budget`. `unknown_count`, `unknown_stops`
and `complete` distinguish missing estimates from free stops. An under result
with unknown prices is only a minimum known cost. `most_expensive_stops` lists
up to three known stops in descending JPY order, with IDs, names, areas, cities
and estimated amounts, to help Planner choose a nearby replacement with Budget.

All checked days share one FX snapshot from `money.convert`, with the same
12-hour cache and explicit stale/offline warning as FX conversion. If all known
costs are zero, no rate is needed. A positive estimate with no usable rate fails
instead of appearing free. Planner may run this read-only command, quote its
over/under result and recheck after changing stops; Budget owns price updates
and spending.

### Receipt images

`spend add ... --receipt PATH` accepts local JPEG, PNG, WebP, GIF, BMP and TIFF
images up to 10 MiB. Both the extension and image contents are checked, including
a real first-frame decode with the existing PyAV dependency. Text, PDFs, videos,
renamed non-images and unreadable/corrupt images are rejected. The CLI does not
read totals or run OCR: Budget must view the image and identify the total and
currency before logging it.

After validation and conversion, the new expense copies the image to
`state/receipts/s_<id>.<original-extension>`, preserving the bytes and extension.
The spend item's `receipt` field is relative to the state directory, for example
`receipts/s_<id>.jpg`; `spend list` includes it in human and JSON output. The
source stays in place. Failed recording removes the new copy; invalid spending,
an invalid image or failed FX never leaves a receipt copy. Omit `--receipt` for
ordinary spending; old entries without the field still list normally. These
files remain under the ignored state directory, including with `TRIPCREW_STATE`.

### Group splits

`trip set --people NAME ...` replaces the people sharing costs, preserving other
settings. Quote multiword names. `spend add ... --paid-by NAME` splits the booked
SGD amount evenly among all listed people; `--split NAME ...` selects the sharers
and requires `--paid-by`. Payer and sharers must be on the trip; matching ignores
case. Duplicate sharers count once. Remainder cents go to the first names in the
split order. The trip budget counts the full expense, not one person's share.

`spend balances` reads saved expenses and suggests SGD transfers to settle up;
it does not record payments. JSON returns `people` (`name`, `paid_sgd`,
`share_sgd`, `net_sgd`), `transfers` (`from`, `to`, `amount_sgd`) and
`unsplit_count`. Expenses without a payer are excluded from balances and counted
as unsplit. Changing the trip's people does not rewrite existing expense shares.

### Voice transcription

`transcribe PATH` reads a local audio file with faster-whisper on CPU/int8;
audio is not uploaded. `--language CODE` sets the spoken language, default `en`.
It prints the transcript, or `ok` and `transcript` with `--json`. A missing file
or no recognized speech fails. The source file is preserved. Transcription does
not record spending: check the amount and currency before using `spend add`.

The model defaults to `small`, overridden with `TRIPCREW_WHISPER_MODEL`. It tries
cached weights first and may download them if unavailable; prepare the model
before running under a network restriction. This command does not download
Telegram attachments; the agent obtains the local file through Switch first.

## State and money

State defaults to the repository's `state/` directory, independent of the caller's
working directory. Set `TRIPCREW_STATE` to an alternate directory. Prefer an
absolute path; relative paths resolve against `tools/` when using the launchers.
Missing JSON files use defaults until their first mutation. The four files are:

- `trip.json`: settings and `days`, an object mapping day numbers to ordered IDs.
- `wishlist.json`: place objects with stable `w_` IDs.
- `spend.json`: expense objects with stable `s_` IDs and original currency.
- `fx.json`: the last successfully fetched JPY-to-SGD rate and its timestamps.

Existing saved trips are preserved; changing the defaults does not clear them.

One `filelock` lock covers complete read/modify/write operations, including
wishlist reference checks. Writes use a flushed and fsynced temporary file in
the same directory followed by atomic replacement. Readers use the same lock
(also avoiding Windows replacement conflicts with open read handles). JSON is
indented UTF-8; stop writers before hand-editing it. Malformed JSON is reported
and preserved rather than overwritten.

Money uses Decimal, with SGD amounts rounded half up to cents. Spending preserves
the original amount and the SGD amount booked using that entry's FX, so a later
rate refresh does not rewrite history. Daily budget shares sum exactly to the
trip budget; extra cents go to the earliest days. Negative amounts left indicate
overspending. `budget status --day` keeps trip totals and filters daily detail.

[Frankfurter's documented v1 endpoint](https://frankfurter.dev/v1/) is
`https://api.frankfurter.dev/v1/latest?base=JPY&symbols=SGD`. v1 is deprecated but
continues to work. Cache lifetime is 12 hours from fetch time, distinct from the
published rate date. An expired cache is refreshed; when offline, the old rate is
used with an explicit age warning. With no usable cache, conversion fails.
Same-currency conversion and SGD spending need no network.

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

Successful trip dates/cities and day add/move send Planner → you cards; budget
or category settings and recorded spending send Budget → you cards. These use
`POST /activity` on the same relay URL, with the same one-second best-effort
timeout. No activity is sent for reads, removals, interests alone or failed writes.
Reusable hook: `from tripcrew import activity`, then
`activity.post_event("budget", "planner", "delegated", "Day 2 is over budget")`.
One call sends one contract `task` card; summaries are flattened and capped at
80 characters. Use `finalised` for completed work, `delegated` for a handoff and
`accepted` for taking it on. The returned payload is not a delivery receipt.

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
