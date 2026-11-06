# Budget CLI reference

Run from `agents/budget/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. `--help` is available on each command. `--json` may be appended for machine output.

| Command | Accepted arguments in this reference | Effect |
| --- | --- | --- |
| `trip show` | none | Read trip settings and day count; JSON also exposes the configured budget. |
| `trip set --budget-sgd AMOUNT` | `--categories NAME=AMOUNT ...` | Set the total budget in SGD and optional categories that add up to it, preserving itinerary fields. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read saved estimated JPY prices and verification/source metadata. |
| `wishlist price ID` | required `--price-jpy AMOUNT\|unknown`, `--source-note NOTE` | Set or update Budget's JPY estimate and its short source note; `0` is free, `unknown` clears it. |
| `spend add AMOUNT JPY\|SGD` | required `--note NOTE`; `--day N` (omit for pre-trip costs such as flights); `--category NAME` (required once categories are set); `--receipt PATH`; `--paid-by NAME`; `--split NAME ...` (even shares; defaults to everyone in `--people`) | Record an expense and booked SGD amount; optionally copy a validated receipt image. |
| `trip set --people NAME ...` | none | Replace who shares costs on this trip; names must be listed here before a spend can be split. |
| `spend list` | none | Read expenses, original currency and booked SGD amounts. |
| `spend balances` | none | Read what each person paid, their share and who pays whom in SGD to settle up. |
| `budget status` | `--day N` | Show total, per-category (with `used_percent` and an 80% `warning`) and daily spending; day filter retains trip totals and categories. |
| `budget check` | `--day N` | Compare planned estimates plus booked daily spending against the evenly split non-flight allowance; omit day for all planned days. |
| `fx convert AMOUNT JPY\|SGD JPY\|SGD` | none | Convert using live or explicitly labelled cached FX. |
| `transcribe PATH` | `--language CODE` (default `en`) | Turn a local audio file into text on CPU without uploading audio; `--json` gives `transcript`. Does not record spending. |

## Windows examples

A fresh state has no budget or dates. Set the budget from the person's request;
the SGD 1,500 split below is an example, not a default. Budget can be set before Planner
sets dates. The spending and daily-status examples require Planner to have
explicitly set dates covering day 2, such as 10–16 December 2026. `budget status`
requires a budget and both dates; `spend add --day` requires both dates. Missing settings
produce a clear error, or `ok: false` and a `reason` with `--json`, without assumed
amounts. Zero is a valid budget.

```powershell
..\..\bin\tripcrew.cmd trip show --json
..\..\bin\tripcrew.cmd trip set --budget-sgd 1500 --categories flight=700 other=800
..\..\bin\tripcrew.cmd wishlist list --city Kyoto --category attraction
..\..\bin\tripcrew.cmd wishlist price w_0123456789ab --price-jpy 1200 --source-note "Official menu; lunch set"
..\..\bin\tripcrew.cmd spend add 1200 JPY --note "Lunch in Kyoto" --day 2 --category other
..\..\bin\tripcrew.cmd spend add 620 SGD --note "Flight" --category flight
..\..\bin\tripcrew.cmd spend list
..\..\bin\tripcrew.cmd budget status --day 2
..\..\bin\tripcrew.cmd budget check --day 2 --json
..\..\bin\tripcrew.cmd fx convert 1000 JPY SGD
```

## sh equivalents

```sh
../../bin/tripcrew trip show --json
../../bin/tripcrew trip set --budget-sgd 1500 --categories flight=700 other=800
../../bin/tripcrew wishlist list --city Kyoto --category attraction
../../bin/tripcrew wishlist price w_0123456789ab --price-jpy 1200 --source-note "Official menu; lunch set"
../../bin/tripcrew spend add 1200 JPY --note "Lunch in Kyoto" --day 2 --category other
../../bin/tripcrew spend add 620 SGD --note "Flight" --category flight
../../bin/tripcrew spend list
../../bin/tripcrew budget status --day 2
../../bin/tripcrew budget check --day 2 --json
../../bin/tripcrew fx convert 1000 JPY SGD
```

Money uses decimal arithmetic. SGD inputs have at most two decimal places; expenses must be positive. Days start at 1. Unknown wishlist prices are distinct from zero/free and are estimates rather than recorded spending. Historical SGD expense amounts retain their original FX. Budget status measures actual spending, not a forecast of wishlist costs.

FX endpoint: `https://api.frankfurter.dev/v1/latest?base=JPY&symbols=SGD`. Cache lifetime is 12 hours from fetch time. Offline conversion uses an old cache with a warning; without a usable cache it fails. Same-currency conversion and SGD expenses need no network. Source: [CLI reference](../../tools/README.md).

## Push back on a planned day

Use the existing wishlist ID when updating an estimate; the examples' ID is a
placeholder. Record the source and context in `--source-note`. Unknown is not
free. `budget check` prints known estimates, actuals, allowance, over/under and
the three most expensive known stops. Its JSON has `over_budget`, `status`,
`difference_sgd` (positive means over), `unknown_count` and `complete` per day.
Unknown prices mean the result is a minimum, even when it says under.

The allowance excludes the `flight` budget category and divides the remaining
categories over all trip days; without categories it divides the total. The
check adds all spending logged for that day at its booked FX. It adds planned
estimates in full, including already-paid stops, because expenses are not
matched to itinerary IDs. No-day pre-trip costs are excluded. FX is live or
explicitly cached/stale, with a single rate shared across the checked days.

When a day is over, tell Planner which wishlist IDs drive it and how much it is
over. Estimate a nearby alternative with a source note so Planner can swap the
stop and rerun `budget check`. Budget does not edit the itinerary.

## Read a receipt photo

1. Take the attachment's `mxc` and original `filename` from the Switch message
   or `read_context`. Call Switch's `download_attachment` with those fields;
   use the returned local path. If Switch already supplied an `image_path`,
   that downloaded image can be viewed directly.
2. View the image itself with Codex's image viewer. Read the final charged total
   and currency, not the subtotal, cash tendered or change. Read the shop name.
   Ask the owner if the amount/currency is unreadable or ambiguous; do not guess.
3. Record it once, using the trip day and a configured category, for example:

   ```powershell
   ..\..\bin\tripcrew.cmd spend add 1200 JPY --receipt "<downloaded-file>.jpg" --note "Shop name" --day 2 --category other
   ```

   ```sh
   ../../bin/tripcrew spend add 1200 JPY --receipt "<downloaded-file>.jpg" --note "Shop name" --day 2 --category other
   ```

The CLI copies the image only while recording the expense. It accepts JPEG,
PNG, WebP, GIF, BMP and TIFF up to 10 MiB and rejects non-images. The original
file is preserved; `spend list` shows `receipts/<spend-id>.<extension>` relative
to shared `state/`. This path is recorded with the spend, not as a separate
wishlist price. Downloads are local files written by Switch; Codex reads them
and the CLI writes only the retained copy into shared `state/receipts/`.

## Split a group expense

Ask who paid if the message doesn't say. Shares are even and in SGD at the rate booked with the expense; leftover cents go to the first names. To split unevenly, log separate expenses. The trip budget counts the full amount, not one person's share.

`--split NAME ...` needs `--paid-by`; omit it to share among everyone in
`--people`. Payer and sharers must be listed on the trip. `spend balances`
suggests transfers without recording payments; expenses with no payer are
counted as unsplit and excluded from balances. Replacing `--people` leaves
existing expense shares unchanged.

```powershell
..\..\bin\tripcrew.cmd trip set --people Woo Ana Ben
..\..\bin\tripcrew.cmd spend add 4137 JPY --receipt "<downloaded-file>.jpg" --note "Shop name" --day 2 --category other --paid-by Woo
..\..\bin\tripcrew.cmd spend balances
```

## Log a voice message

1. Take the attachment's `mxc` and `filename` (usually `voice.ogg`) from the Switch message or `read_context`, and call Switch's `download_attachment`.
2. Run `transcribe` on the returned path. It defaults to English (`en`); pass `--language CODE` for another spoken language. It tries cached model weights first and may download them if missing, so prepare the model before using a restricted network.
3. Log the amount, currency and item from the transcript with `spend add`, then repeat them in your reply so the owner can catch a mishearing. Names of foods and places are the likeliest to be wrong: fix an obvious one and say so. If the amount or currency is unclear, ask and don't log.

```powershell
..\..\bin\tripcrew.cmd transcribe "<downloaded-file>.ogg" --json
```

## Solo or group trip

If `trip show --json` lists `people`, it's a group trip with its own budget; with no people, it's solo and nothing is split. On a group trip, a place's price on the wishlist and in `budget check` covers the whole group: multiply a per-person price by the number of people and say so in `--source-note`. Log a group expense with `--paid-by`, and when the owner asks who owes what, run `spend balances` and show the result.

A voice message or receipt photo may arrive with no text. Treat a voice message about money as a spend to log.
