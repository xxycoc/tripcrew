# Reel Adder CLI reference

Run from `agents/reel-adder/`. Windows PowerShell uses `..\..\bin\tripcrew.cmd`; sh uses `../../bin/tripcrew`. `--help` is available on each command. `--json` may be appended; `reel fetch` always returns JSON.

| Command | Accepted arguments | Effect |
| --- | --- | --- |
| `trip show` | none | Read trip cities and dates. |
| `wishlist list` | `--city CITY`, `--category food\|attraction\|tip`, `--unplanned` | Read existing places and sources, including possible duplicates. |
| `reel fetch URL` | `--audio` | Extract TikTok/Instagram metadata; short captions or `--audio` trigger audio transcription. |
| `wishlist add` | required `--name NAME --area AREA --city CITY --category food\|attraction\|tip`; optional `--price-jpy AMOUNT --hours HOURS --url URL --verified --note NOTE --reel` | Save a source-backed place. Returns its new `w_` ID. |
| `reel identified` | required `--place "Name, area"`; optional `--platform tiktok\|instagram` | Submit an identified event to the relay. |
| `reel failed` | required `--reason REASON`; optional `--platform tiktok\|instagram` | Submit a failed event to the relay. |

## Windows examples

A fresh state has no trip cities or dates. `trip show` reports this and gives
setup flags; ask the person for missing trip context and let Planner set it.
Wishlist and reel commands work before trip setup. Kyoto below is an explicit
example filter and place city, not a default destination.

The fetch URL is an upstream yt-dlp TikTok test example, independent of the shrine example below; its current availability was not tested. The commands illustrate separate operations.

```powershell
..\..\bin\tripcrew.cmd trip show
..\..\bin\tripcrew.cmd wishlist list --city Kyoto --category attraction
..\..\bin\tripcrew.cmd reel fetch "https://www.tiktok.com/@leenabhushan/video/6748451240264420610" --audio
..\..\bin\tripcrew.cmd wishlist add --name "Fushimi Inari Taisha" --area Fushimi --city Kyoto --category attraction --price-jpy 0 --hours "Grounds open year-round; daily hours not confirmed" --url "https://www.the-kansai-guide.com/en/directory/item/11818/" --verified --note "Shrine admission; shop hours not verified" --reel
..\..\bin\tripcrew.cmd reel identified --place "Fushimi Inari Taisha, Fushimi" --platform instagram
..\..\bin\tripcrew.cmd reel failed --reason "Person could not provide a clearer caption or location" --platform instagram
```

## sh equivalents

```sh
../../bin/tripcrew trip show
../../bin/tripcrew wishlist list --city Kyoto --category attraction
../../bin/tripcrew reel fetch "https://www.tiktok.com/@leenabhushan/video/6748451240264420610" --audio
../../bin/tripcrew wishlist add --name "Fushimi Inari Taisha" --area Fushimi --city Kyoto --category attraction --price-jpy 0 --hours "Grounds open year-round; daily hours not confirmed" --url "https://www.the-kansai-guide.com/en/directory/item/11818/" --verified --note "Shrine admission; shop hours not verified" --reel
../../bin/tripcrew reel identified --place "Fushimi Inari Taisha, Fushimi" --platform instagram
../../bin/tripcrew reel failed --reason "Person could not provide a clearer caption or location" --platform instagram
```

## Extraction and verification

The supported sequence is fetch, independent WebSearch/WebFetch verification of name, area, opening hours and price, wishlist addition with `--reel`, then identified. `--reel` skips the automatic wishlist handoff card because the following `reel identified` already animates the same place. Omit `--reel` for a standalone wishlist addition. Metadata and machine transcripts are clues, not external verification. Unknown hours can be omitted; an unknown price is omitted, while `0` means free. `--verified` records the agent's source check; the CLI does not perform it. The shrine example uses the [official Kansai tourism listing](https://www.the-kansai-guide.com/en/directory/item/11818/).

An unresolved result requires a question to the person before a failed event. Fetch errors do not post failed automatically. After a successful addition, the chat handoff names `planner` and `budget` and includes the returned wishlist ID and source. There is no CLI chat-send command.

Fetch returns `ok: false` on failure, with available metadata/reason, and exits 1. Audio-only streams may be unavailable; transcription may download model weights on first use. Temporary audio is cleaned up. Cookies are read only if explicitly configured. Relay events are best-effort submissions to `TRIPCREW_RELAY_URL` (default `http://127.0.0.1:8771`), not delivery receipts. Source: [CLI reference](../../tools/README.md).
