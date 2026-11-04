# Planner CLI reference

Run from `agents/planner/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. The examples below show both forms. `--help` is available on each command. `--json` may be appended for machine output.

`trip show` human output omits prices; its JSON includes `budget_sgd`. `wishlist list` includes stored price metadata in both output formats. Dates are inclusive. Days and positions start at 1. Wishlist IDs come from `wishlist list`; `w_0123456789ab` below stands for an existing returned ID.

| Command | Accepted arguments in this reference | Effect |
| --- | --- | --- |
| `trip show` | none | Read dates, cities, interests and ordered stops. |
| `trip set` | `--start YYYY-MM-DD`, `--end YYYY-MM-DD`, `--cities CITY [CITY ...]`, `--interests INTEREST [INTEREST ...]` | Replace supplied itinerary settings; preserve omitted fields. The budget flag is excluded. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read places, source URLs and opening hours; optionally filter unplanned entries. |
| `trip day N add ID` | `--position N` | Add an existing wishlist place; default append. |
| `trip day N remove ID` | none | Remove a stop from that day, retaining its wishlist entry. |
| `trip day N move ID` | `--position N`, `--to-day N` | Reorder or move a stop; position is its final position after removal. |
| `budget check` | `--day N` | Read Budget's day cost check: over/under, difference, unknown prices and most expensive planned stops. No price or spend edits. |

## Windows examples

A fresh state has no trip. Use the person's Telegram messages to set dates,
cities and interests; the values below are examples, not defaults. `trip show`
explains setup when empty and supports partial settings. Both dates must be set
before editing itinerary days. Budget sets the budget separately.

```powershell
..\..\bin\tripcrew.cmd trip show
..\..\bin\tripcrew.cmd trip set --start 2026-12-10 --end 2026-12-16 --cities Osaka Kyoto --interests food temples
..\..\bin\tripcrew.cmd wishlist list --city Kyoto --category attraction --unplanned
..\..\bin\tripcrew.cmd trip day 1 add w_0123456789ab --position 1
..\..\bin\tripcrew.cmd trip day 1 move w_0123456789ab --to-day 2 --position 1
..\..\bin\tripcrew.cmd trip day 2 remove w_0123456789ab
..\..\bin\tripcrew.cmd budget check --day 2 --json
```

## sh equivalents

```sh
../../bin/tripcrew trip show
../../bin/tripcrew trip set --start 2026-12-10 --end 2026-12-16 --cities Osaka Kyoto --interests food temples
../../bin/tripcrew wishlist list --city Kyoto --category attraction --unplanned
../../bin/tripcrew trip day 1 add w_0123456789ab --position 1
../../bin/tripcrew trip day 1 move w_0123456789ab --to-day 2 --position 1
../../bin/tripcrew trip day 2 remove w_0123456789ab
../../bin/tripcrew budget check --day 2 --json
```

Changes that would exclude planned stops or recorded expenses fail. A move to a day already containing that ID also fails. Source: [CLI reference](../../tools/README.md).

## Work with Budget on an expensive day

Planner never quotes prices or makes its own estimates. It may repeat amounts
printed by `budget check`, including how much a day is over or under. Budget
owns the estimates and all recorded spending; request missing or updated
estimates from Budget.

Run `budget check --day N` after filling or changing a day; omit `--day` to
check every planned day. When over, use the returned stop IDs, areas and cities
to find a nearby alternative, ask Budget to estimate it, swap stops with the
existing itinerary commands, then recheck. Do not infer an alternative's price
from location or category. Only repeat money amounts from the check output.

The check adds known planned estimates to booked spending and compares that
against the non-flight daily allowance. It does not match already-paid stops
to expenses. `unknown_count` above zero and `complete: false` mean the result
is incomplete, even when `status` says under. Preserve any FX stale warning.
This command cannot change the trip, prices or spending; it may refresh FX cache.
