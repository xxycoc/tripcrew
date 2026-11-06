# Viewer relay

Python 3.12+ and `uv` are required. From the repository root:

```powershell
# This also avoids shared-cache permission failures on restricted Windows hosts.
$env:UV_CACHE_DIR = Join-Path (Get-Location) 'relay/.local/uv-cache'
uv run --directory relay python -m relay demo
```

The game connects to `ws://127.0.0.1:8770/`. Every connection gets `hello`,
the existing `switch_on` if any, then the latest `board` (initially empty).
Demo loops the TikTok identification, failed Instagram reel, and task handoff.
Its `hello.mode` is always `demo`. Stop with Ctrl+C.

## Register and run live

1. In Switch Console select the server, then **Full admin interface → Open**.
   In the dashboard select **API Keys → Create Registration Key**, supply a label,
   click **Create**, and copy the new key. This is a registration token, not an
   agent key. Native local servers may have no dashboard; an operator must supply
   a personal registration key or the deployment's bootstrap registration token.
2. Get the **agent bridge** URL. For externally connected servers, Console's
   server menu **Edit connection… → Server address** shows the configured URL;
   use that only if its `/health` is the bridge probe.
   A separate Gateway/dashboard origin is not the bridge. Ask the operator for
   the bridge origin if needed. Registration probes `/health` before sending the token.
3. Copy and edit the local config. Set the bridge URL, unique Viewer name, and
   `[actors]` with actual participant IDs/names. Add each room's explicit aliases
   under `[mentions]`. Include agent IDs in `[actors]` for legacy task frames.

```powershell
Copy-Item relay/relay.example.toml relay/relay.local.toml
# Edit relay/relay.local.toml before registering.
# Set SWITCH_REGISTRATION_TOKEN in this shell to the copied token.
uv run --directory relay python -m relay register
Remove-Item Env:SWITCH_REGISTRATION_TOKEN
uv run --directory relay python -m relay live
```

Alternatively pass the token with `register --token <registration-token>`;
the environment variable avoids putting it in shell history or process arguments.
Registration uses `POST /agents` with `connector_type=custom`, an `always_on`
integration profile and `message_exchange=false`, rather than claiming to be a
Claude/Codex provider at `/agents/register-known`. It saves the returned agent ID
and API key in `relay/.local/viewer.json`, bound to the bridge and Viewer name.
It refuses to overwrite an existing key file or server registration.
`relay.local.toml` and `.local/` are gitignored. Keep other local configs named
`*.local.toml` and keep credentials under `.local/`.

After registration, in Console open **Your Agents**, choose the registered Viewer,
then **Add to room** and choose the TripCrew room. The channel alternative is
`!invite-agent @custom.viewer.owner` (use your actual registered name).
The relay itself never sends that command. Live mode makes no operation calls,
claims no rooms, and only posts connection heartbeats to Switch. The separate
[morning brief command](morning-brief.md) can post a message as this same Viewer.
For that brief, set Planner and Budget's **Who can talk to your agent** to
**Anyone** in Console's **Agent settings**. The Viewer is not counted as an agent
you own; otherwise Switch accepts the post but logs `Addressing denied` and the
agents never receive it.

The Viewer opens SSE with `scope=all&filter=all`, starts at `head`, keeps a UUID
across reconnects, reads the server heartbeat interval, and beats with its cursor
and generation when provided. Reconnect uses `Last-Event-ID` and capped exponential
backoff; dead/no-stream heartbeat responses reopen immediately. A gap logs missing
history and adopts the server cursor. Authentication errors and a fenced takeover
stop the process. Cursor and board live in memory; restarting starts a new live
observation, not a replay of earlier sessions.

## Reel and activity intakes and checks

```powershell
$body = @{ type='reel'; step='identified'; platform='tiktok'; place='Kushikatsu Daruma, Shinsekai' } | ConvertTo-Json
Invoke-WebRequest http://127.0.0.1:8771/reel -Method Post -ContentType application/json -Body $body
$activity = @{ type='task'; from='planner'; to='you'; state='finalised'; summary='Day 2: Hiraoka Park' } | ConvertTo-Json
Invoke-WebRequest http://127.0.0.1:8771/activity -Method Post -ContentType application/json -Body $activity
uv run --directory relay python -m pytest -q
```

Valid activity intake returns 204 and broadcasts `task` then the rolling six-line
`board`, with one `from → to: summary` line capped at 80 characters. `/activity`
accepts only contract actors, `delegated`/`accepted`/`finalised`, and a nonblank
single-line string summary of at most 80 characters. Extra fields are ignored;
the relay sets `v` and `ts`. `/reel` is unchanged: progress broadcasts only `reel`,
and identified/failed outcomes also update the board.
Invalid bodies return 400; bodies over 64 KiB return 413. Both servers bind only to
loopback; ports are configurable. All events follow [the game contract](events.md).
Tools use `TRIPCREW_RELAY_URL` (default `http://127.0.0.1:8771`) for both routes,
with a one-second timeout and silent failure. Successful local writes remain
successful when the relay is offline. `tripcrew.activity.post_event(from_actor,
to_actor, state, summary)` submits one card and normalizes/caps its summary.
The project is not packaged and `uv` builds are disabled, including dependencies.
Tests use fake servers on loopback and require no internet or running Switch.

## Source limitations

- `payload.addressed` is receiver-specific. A Viewer's flag cannot identify other
  agents. We match explicit `@registered-name` and configured `@alias` text only,
  once per actor. This records textual addressing, not a guarantee Switch permitted
  or delivered it. Role mentions and targets absent from the body cannot be
  recovered from this event envelope. Unknown senders and platform posts are dropped.
- The checked-out server has retired all `task_*` producers. The mapper supports
  the documented legacy `task_delegate`, `task_accept`, and `task_finalise` frames
  if delivered. `task_update` and `task_cancel` have no contract state and are dropped.
  Older task delivery is one-sided to requester/performer, so a separate Viewer
  cannot observe those private frames. Successful shared CLI writes now provide
  observable activity through `/activity`; they report saved work, not internal
  thinking or guaranteed chat delivery. Demo tasks are explicitly synthetic.
- `switch_on` means a stream was opened at least once. The contract has no
  disconnection or history-gap event. Neither status is invented as game activity.

Protocol reference: [Switch agent protocol](https://docs.switchagents.ai/flintai/switch/internals/agent-protocol).
The local server code takes precedence over its older published task description.
