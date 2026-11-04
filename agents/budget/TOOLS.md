# Budget CLI reference

Run from `agents/budget/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. `--help` is available on each command. `--json` may be appended for machine output.

| Command | Accepted arguments in this reference | Effect |
| --- | --- | --- |
| `trip show` | none | Read trip settings and day count; JSON also exposes the configured budget. |
| `trip set --budget-sgd AMOUNT` | `--categories NAME=AMOUNT ...` | Set the total budget in SGD and optional categories that add up to it, preserving itinerary fields. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read saved estimated JPY prices and verification/source metadata. |
| `spend add AMOUNT JPY\|SGD` | required `--note NOTE`; `--day N` (omit for pre-trip costs such as flights); `--category NAME` (required once categories are set) | Record an expense and the SGD amount booked at entry time. |
| `spend list` | none | Read expenses, original currency and booked SGD amounts. |
| `budget status` | `--day N` | Show total, per-category (with `used_percent` and an 80% `warning`) and daily spending; day filter retains trip totals and categories. |
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
..\..\bin\tripcrew.cmd spend add 1200 JPY --note "Lunch in Kyoto" --day 2 --category other
..\..\bin\tripcrew.cmd spend add 620 SGD --note "Flight" --category flight
..\..\bin\tripcrew.cmd spend list
..\..\bin\tripcrew.cmd budget status --day 2
..\..\bin\tripcrew.cmd fx convert 1000 JPY SGD
```

## sh equivalents

```sh
../../bin/tripcrew trip show --json
../../bin/tripcrew trip set --budget-sgd 1500 --categories flight=700 other=800
../../bin/tripcrew wishlist list --city Kyoto --category attraction
../../bin/tripcrew spend add 1200 JPY --note "Lunch in Kyoto" --day 2 --category other
../../bin/tripcrew spend add 620 SGD --note "Flight" --category flight
../../bin/tripcrew spend list
../../bin/tripcrew budget status --day 2
../../bin/tripcrew fx convert 1000 JPY SGD
```

Money uses decimal arithmetic. SGD inputs have at most two decimal places; expenses must be positive. Days start at 1. Unknown wishlist prices are distinct from zero/free and are estimates rather than recorded spending. Historical SGD expense amounts retain their original FX. Budget status measures actual spending, not a forecast of wishlist costs.

FX endpoint: `https://api.frankfurter.dev/v1/latest?base=JPY&symbols=SGD`. Cache lifetime is 12 hours from fetch time. Offline conversion uses an old cache with a warning; without a usable cache it fails. Same-currency conversion and SGD expenses need no network. Source: [CLI reference](../../tools/README.md).
