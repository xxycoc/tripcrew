# Morning brief

The owner's laptop asks Planner and Budget for a brief each morning. Planner
answers with today's plan; Budget answers with money left, following their own
instructions. Windows Task Scheduler launches one Viewer post, then exits. The
game and live relay do not need to be running. Switch and the answering agents
must be available.

## Setup

Use the [existing Viewer setup](relay.md#register-and-run-live). Do not register
another Viewer. Prepare `relay/.venv` with the relay dependencies, and keep its
existing key at `relay/.local/viewer.json` (or `switch.api_key_path`). Both the key
and `relay/relay.local.toml` stay gitignored. In that config's `[switch]` section,
add `room_id = "YOUR_SWITCH_ROOM_ID"`. Use the room's Switch ID from the room
details in the dashboard, not Telegram's chat ID. The Viewer must already belong
to that room; `planner` and `budget` must be its agents' room aliases.

In Switch Console, open **Agent settings** for Planner and Budget and set
**Who can talk to your agent** to **Anyone**. The Viewer is not counted as an
agent you own. With **Only me and my agents**, Switch accepts the post but logs
`Addressing denied`; Planner and Budget never receive the request.

A custom connector with an `always_on` profile
and `message_exchange=false` can post using its existing API key. No registration
or profile change is needed on the checked-out Switch server. Posting still
requires room membership and is subject to Switch's spending and trust checks.

The launchers use the prepared virtual environment directly, without installing
dependencies or relying on `uv` being on the scheduled task's PATH. They change
to the repository root and append stdout and stderr to `relay/.local/brief.log`.
Exit 0 means Switch accepted a message and returned an event ID. It does not
confirm Telegram delivery or an agent answer. Failures exit 1.

## Try once and schedule

These commands post to the configured room. Run them only when ready to send.
From the repository root in PowerShell:

```powershell
# Post today's generated brief immediately, without installing a task.
bin\morning-brief.cmd
Get-Content relay/.local/brief.log -Tail 20

# Register a daily task for this Windows user. Default is 08:00 local time.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/brief-task.ps1 install -At 08:00
# Trigger the installed task once now. This returns before posting completes.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/brief-task.ps1 run
# Remove just this user's morning brief task.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/brief-task.ps1 uninstall
```

`-ExecutionPolicy Bypass` applies to that PowerShell process only, allowing the
reviewed local script to run where scripts are disabled; it saves no machine or
user execution-policy change.

The task is named `TripCrew-MorningBrief-<Windows SID>` and runs with the current
user's interactive token and limited privileges, only while logged on. No
password is saved and no administrator session is requested. The laptop must be
awake at the scheduled time; the task does not wake it or catch up missed runs.
Battery operation is allowed. Overlapping task instances are ignored; there is
no automatic retry. To change time or checkout location, uninstall then install
from the intended checkout. Installation refuses to replace an existing task.
Check **Last Run Result** in Task Scheduler as well as the log after `run`.

The task runs daily until removed. When local today's date falls within the
inclusive dates in `state/trip.json`, its one-line message includes the trip day
(starting at 1). Outside those dates, or before both dates are set, it explicitly
requests a **test brief**. Uninstall after the trip to stop those test requests.
Malformed saved state fails instead of guessing. `TRIPCREW_STATE` overrides the
state directory; relative overrides resolve from the repo root in the launchers.
The date and scheduled time use the laptop's local timezone, including after a
timezone change. Keep the laptop's date/timezone aligned with the trip.

The editable message lives once in `relay/relay/brief.py` as `BRIEF_TEXT`:

```text
@planner @budget Morning brief for trip day 2 (2026-12-11): please share today's plan and money left, each per your instructions.
```

On sh, use `sh bin/morning-brief` (or `bin/morning-brief` when executable).
Both launchers accept the post command's arguments, such as `--room ROOM_ID` or
`--json`. An explicit quoted message replaces the generated brief.

## Direct post command

```powershell
cd relay
.venv\Scripts\python.exe -m relay post
.venv\Scripts\python.exe -m relay post --room ROOM_ID "@planner @budget Please share today's brief."
.venv\Scripts\python.exe -m relay --config relay.local.toml post --json
```

`post` accepts an optional message, `--room`, `--config` and `--json`. Omit the
room to use `switch.room_id`; omit text to generate the brief. JSON success has
`ok`, `room_id`, `event_id`; errors have `ok: false` and `reason`. Human output uses
short labelled lines. No key is printed or passed on the command line. A missing
config, room, key, HTTP rejection or invalid receipt fails clearly. HTTP errors
report status without echoing response bodies. Redirects are refused. A timeout
or invalid receipt leaves delivery unknown: check the room before retrying to
avoid duplicate requests.

## Switch source check

In the checked-out Switch source, `bridges/agent/api/handlers.py` defines
`POST /agents/{agent_id}/message`, taking `room_id` and `content` with a Bearer
agent API key; it calls `AgentCore.send_message` directly. No SSE connection or
room claim is required. The operation alternative `post_message` depends on a
connected room, so this one-shot command uses the direct message endpoint.
`message_exchange` is profile information, not a posting gate on this path.
Room aliases provide the explicit mentions. The live Viewer did not qualify for
the addressing policy's `owner_agents` rule; use **Anyone** as described above.

See the official [agent protocol](https://docs.switchagents.ai/flintai/switch/internals/agent-protocol),
[identity and access](https://docs.switchagents.ai/flintai/switch/internals/identity-and-access),
and [message path](https://docs.switchagents.ai/flintai/switch/internals/life-of-a-message).
The local server source takes precedence if a deployed version differs. Fake
server tests verify the request and CLI; they do not establish live delivery.
