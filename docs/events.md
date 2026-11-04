# Game event contract

The relay sends these to the game over WebSocket at `ws://127.0.0.1:8770`, one JSON object per text frame. Every event has `v` (always `1`), `type` and `ts` (ISO 8601 UTC). Unknown types and fields are ignored, so either side can grow.

Actors are `planner`, `budget`, `reel_adder` and `you`. The relay maps Switch agent names and the human sender to actors through its config. Anything it can't map is dropped.

| `type` | Fields | Source | On screen |
|---|---|---|---|
| `hello` | `mode`: `live` or `demo` | Relay, on connect | Nothing. The game shows "DEMO FEED" in a corner while `mode` is `demo`. |
| `switch_on` | | Relay, once its Switch stream is open | Hall lights up, doors unlock |
| `join` | `actor` | Switch `room_join` | Agent climbs down to the hall once, then returns |
| `user_message` | `text` | Switch `message` from the person | You walk in from the right with a note |
| `addressed` | `actor`, `text` | Switch `message` that addresses an agent | That room's light turns on and the agent works at its desk until it speaks |
| `agent_message` | `actor`, `text` (first line, max 80 chars) | Switch `message` from an agent | Agent climbs down to the hall and shows a speech bubble |
| `task` | `from`, `to`, `state`: `delegated`, `accepted` or `finalised`, `summary` | Switch `task_*` | A card passes between the two characters |
| `reel` | `step`: `fetch_start`, `watching`, `identified` or `failed`, plus `platform` (`tiktok`, `instagram`), `place`, `reason` as available | The `tripcrew reel` CLI, via `POST http://127.0.0.1:8771/reel` | `fetch_start`: Reel Adder runs out the red TikTok/IG door. `watching`: sits in the screening room. `identified`: runs back with a pin card to Planner. `failed`: comes back with a "?" bubble and walks to you. |
| `board` | `lines`: up to 6 short strings | Relay, after each message or reel event | The hall's wall board |

`POST /reel` takes the same body as a `reel` event without `v` and `ts` and returns `204`. The relay adds `v` and `ts` and broadcasts it. If the relay isn't running, the CLI carries on without it.

## Example

```json
{"v":1,"type":"reel","ts":"2026-11-05T03:12:09Z","step":"identified","platform":"tiktok","place":"Kushikatsu Daruma, Shinsekai"}
```
