# Planner CLI reference

Run from `agents/planner/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. The examples below show both forms. `--help` is available on each command. `--json` may be appended for machine output.

`trip show` human output omits prices; its JSON includes `budget_sgd`. `wishlist list` includes stored price metadata in both output formats. Dates are inclusive. Days and positions start at 1. Wishlist IDs come from `wishlist list`; `w_0123456789ab` below stands for an existing returned ID.

| Command | Accepted arguments in this reference | Effect |
| --- | --- | --- |
| `trip show` | none | Read dates, cities, interests and ordered stops. |
| `trip map` | optional day `N` | Read one Google Maps link per planned day, or just day N; JSON includes the stops used. |
| `trip set` | `--start YYYY-MM-DD`, `--end YYYY-MM-DD`, `--cities CITY [CITY ...]`, `--interests INTEREST [INTEREST ...]` | Replace supplied itinerary settings; preserve omitted fields. The budget flag is excluded. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read places, source URLs and opening hours; optionally filter unplanned entries. |
| `trip day N add ID` | `--position N` | Add an existing wishlist place; default append. |
| `trip day N remove ID` | none | Remove a stop from that day, retaining its wishlist entry. |
| `trip day N move ID` | `--position N`, `--to-day N` | Reorder or move a stop; position is its final position after removal. |

## Windows examples

A fresh state has no trip. Use the person's Telegram messages to set dates,
cities and interests; the values below are examples, not defaults. `trip show`
explains setup when empty and supports partial settings. Both dates must be set
before editing itinerary days. Budget sets the budget separately.

```powershell
..\..\bin\tripcrew.cmd trip show
..\..\bin\tripcrew.cmd trip map 2
..\..\bin\tripcrew.cmd trip map --json
..\..\bin\tripcrew.cmd trip set --start 2026-12-10 --end 2026-12-16 --cities Osaka Kyoto --interests food temples
..\..\bin\tripcrew.cmd wishlist list --city Kyoto --category attraction --unplanned
..\..\bin\tripcrew.cmd trip day 1 add w_0123456789ab --position 1
..\..\bin\tripcrew.cmd trip day 1 move w_0123456789ab --to-day 2 --position 1
..\..\bin\tripcrew.cmd trip day 2 remove w_0123456789ab
```

## sh equivalents

```sh
../../bin/tripcrew trip show
../../bin/tripcrew trip map 2
../../bin/tripcrew trip map --json
../../bin/tripcrew trip set --start 2026-12-10 --end 2026-12-16 --cities Osaka Kyoto --interests food temples
../../bin/tripcrew wishlist list --city Kyoto --category attraction --unplanned
../../bin/tripcrew trip day 1 add w_0123456789ab --position 1
../../bin/tripcrew trip day 1 move w_0123456789ab --to-day 2 --position 1
../../bin/tripcrew trip day 2 remove w_0123456789ab
```

Changes that would exclude planned stops or recorded expenses fail. A move to a day already containing that ID also fails. Source: [CLI reference](../../tools/README.md).

For day summaries, use `trip map N` to include that day's tap-able link. It reads
names, areas and cities in itinerary order; one stop opens search, multiple stops
request transit directions. Dates are required. Unplanned days return a message
instead of a link. The mobile browser limit is three waypoints, so only the first
five stops are included; keep any omission warning with the link. `trip map`
lists planned days only, in day order. No state is changed and no source URLs are
parsed. Maps may ignore unsupported waypoints; links are not verified routes.
