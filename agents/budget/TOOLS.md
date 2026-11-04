# Budget CLI reference

Run from `agents/budget/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. `--help` is available on each command. `--json` may be appended for machine output.

| Command | Accepted arguments in this reference | Effect |
| --- | --- | --- |
| `trip show` | none | Read trip settings and day count; JSON also exposes the configured budget. |
| `trip set --budget-sgd AMOUNT` | `--categories NAME=AMOUNT ...` | Set the total budget in SGD and optional categories that add up to it, preserving itinerary fields. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read saved estimated JPY prices and verification/source metadata. |
| `wishlist price ID` | required `--price-jpy AMOUNT\|unknown`, `--source-note NOTE` | Set or update Budget's JPY estimate and its short source note; `0` is free, `unknown` clears it. |
| `spend add AMOUNT JPY\|SGD` | required `--note NOTE`; `--day N` (omit for pre-trip costs such as flights); `--category NAME` (required once categories are set); `--receipt PATH` | Record an expense and booked SGD amount; optionally copy a validated receipt image. |
| `spend list` | none | Read expenses, original currency and booked SGD amounts. |
| `budget status` | `--day N` | Show total, per-category (with `used_percent` and an 80% `warning`) and daily spending; day filter retains trip totals and categories. |
| `budget check` | `--day N` | Compare planned estimates plus booked daily spending against the evenly split non-flight allowance; omit day for all planned days. |
| `fx convert AMOUNT JPY\|SGD JPY\|SGD` | none | Convert using live or explicitly labelled cached FX. |

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
