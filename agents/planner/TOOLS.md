# Planner CLI reference

Run from `agents/planner/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. The examples below show both forms. `--help` is available on each command. `--json` may be appended for machine output.

`trip show` human output omits prices; its JSON includes `budget_myr`. `wishlist list` includes stored price metadata in both output formats. Dates are inclusive. Days and positions start at 1. Wishlist IDs come from `wishlist list`; `w_0123456789ab` below stands for an existing returned ID.

| Command | Accepted arguments in this reference | Effect |
| --- | --- | --- |
| `trip show` | none | Read dates, cities, interests and ordered stops. |
| `trip set` | `--start YYYY-MM-DD`, `--end YYYY-MM-DD`, `--cities CITY [CITY ...]`, `--interests INTEREST [INTEREST ...]` | Replace supplied itinerary settings; preserve omitted fields. The budget flag is excluded. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read places, source URLs and opening hours; optionally filter unplanned entries. |
| `trip day N add ID` | `--position N` | Add an existing wishlist place; default append. |
| `trip day N remove ID` | none | Remove a stop from that day, retaining its wishlist entry. |
| `trip day N move ID` | `--position N`, `--to-day N` | Reorder or move a stop; position is its final position after removal. |

## Windows examples

```powershell
..\..\bin\tripcrew.cmd trip show
..\..\bin\tripcrew.cmd trip set --start 2026-12-10 --end 2026-12-16 --cities Osaka Kyoto --interests food temples
..\..\bin\tripcrew.cmd wishlist list --city Kyoto --category attraction --unplanned
..\..\bin\tripcrew.cmd trip day 1 add w_0123456789ab --position 1
..\..\bin\tripcrew.cmd trip day 1 move w_0123456789ab --to-day 2 --position 1
..\..\bin\tripcrew.cmd trip day 2 remove w_0123456789ab
```

## sh equivalents

```sh
../../bin/tripcrew trip show
../../bin/tripcrew trip set --start 2026-12-10 --end 2026-12-16 --cities Osaka Kyoto --interests food temples
../../bin/tripcrew wishlist list --city Kyoto --category attraction --unplanned
../../bin/tripcrew trip day 1 add w_0123456789ab --position 1
../../bin/tripcrew trip day 1 move w_0123456789ab --to-day 2 --position 1
../../bin/tripcrew trip day 2 remove w_0123456789ab
```

Changes that would exclude planned stops or recorded expenses fail. A move to a day already containing that ID also fails. Source: [CLI reference](../../tools/README.md).
