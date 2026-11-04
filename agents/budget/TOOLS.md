# Budget CLI reference

Run from `agents/budget/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. `--help` is available on each command. `--json` may be appended for machine output.

| Command | Accepted arguments in this reference | Effect |
| --- | --- | --- |
| `trip show` | none | Read trip settings and day count; JSON also exposes the configured budget. |
| `trip set --budget-myr AMOUNT` | budget flag only | Set the total budget in MYR, preserving itinerary fields. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read saved estimated JPY prices and verification/source metadata. |
| `spend add AMOUNT JPY\|MYR` | required `--note NOTE --day N` | Record an expense and the MYR amount booked at entry time. |
| `spend list` | none | Read expenses, original currency and booked MYR amounts. |
| `budget status` | `--day N` | Show total and daily budget, spending and money left; day filter retains trip totals. |
| `fx convert AMOUNT JPY\|MYR JPY\|MYR` | none | Convert using live or explicitly labelled cached FX. |

## Windows examples

```powershell
..\..\bin\tripcrew.cmd trip show --json
..\..\bin\tripcrew.cmd trip set --budget-myr 6000.00
..\..\bin\tripcrew.cmd wishlist list --city Kyoto --category attraction
..\..\bin\tripcrew.cmd spend add 1200 JPY --note "Lunch in Kyoto" --day 2
..\..\bin\tripcrew.cmd spend list
..\..\bin\tripcrew.cmd budget status --day 2
..\..\bin\tripcrew.cmd fx convert 1000 JPY MYR
```

## sh equivalents

```sh
../../bin/tripcrew trip show --json
../../bin/tripcrew trip set --budget-myr 6000.00
../../bin/tripcrew wishlist list --city Kyoto --category attraction
../../bin/tripcrew spend add 1200 JPY --note "Lunch in Kyoto" --day 2
../../bin/tripcrew spend list
../../bin/tripcrew budget status --day 2
../../bin/tripcrew fx convert 1000 JPY MYR
```

Money uses decimal arithmetic. MYR inputs have at most two decimal places; expenses must be positive. Days start at 1. Unknown wishlist prices are distinct from zero/free and are estimates rather than recorded spending. Historical MYR expense amounts retain their original FX. Budget status measures actual spending, not a forecast of wishlist costs.

FX endpoint: `https://api.frankfurter.dev/v1/latest?base=JPY&symbols=MYR`. Cache lifetime is 12 hours from fetch time. Offline conversion uses an old cache with a warning; without a usable cache it fails. Same-currency conversion and MYR expenses need no network. Source: [CLI reference](../../tools/README.md).
