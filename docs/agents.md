# Agent working folders

Switch Console starts each provider in its own folder. Replace `<owner>` with the owner's Switch name suffix.

| Agent | Folder | Provider | Suggested Switch name | Alias | Tool reference |
| --- | --- | --- | --- | --- | --- |
| Planner | `agents/planner` | Claude Code | `claude-code.tripcrew-planner.<owner>` | `planner` | [TOOLS.md](../agents/planner/TOOLS.md): trip settings excluding budget, ordered itinerary stops, wishlist reads. |
| Budget | `agents/budget` | Codex | `codex.tripcrew-budget.<owner>` | `budget` | [TOOLS.md](../agents/budget/TOOLS.md): budget and people settings, prices, expenses and group balances, local voice transcription, budget status and JPY/SGD FX; trip/wishlist reads. |
| Reel Adder | `agents/reel-adder` | Claude Code | `claude-code.tripcrew-reel-adder.<owner>` | `reel` | [TOOLS.md](../agents/reel-adder/TOOLS.md): extraction, source verification, wishlist addition and relay outcome events; trip/wishlist reads. |

For **each** Console agent choose:

- Who can talk to your agent: **Anyone** for Planner and Budget when using the [morning brief](morning-brief.md); **Only me and my agents** otherwise.
- Auto mode: **On**.
- Bypass: **Off**.
- Working directory: the corresponding folder above, not the repository root.

The two `CLAUDE.md` files and Budget's `AGENTS.md` hold the owner's voice-dictated instructions (Wispr Flow), with only transcription slips corrected.

The Viewer is not counted as an agent you own. Without **Anyone**, Switch can
accept its brief post but log `Addressing denied`, so Planner and Budget never
receive the request.

## Group costs and voice messages

Budget uses `trip set --people NAME ...` to replace the people sharing costs.
`spend add AMOUNT JPY|SGD --note NOTE --paid-by NAME` splits the booked SGD amount
evenly among those people; `--split NAME ...` selects a subset and requires
`--paid-by`. Payer and sharers must be on the trip. `spend balances` shows paid
amounts, shares and suggested SGD transfers; expenses without a payer are counted
as unsplit and excluded from balances. The trip budget still counts each full
expense.

`transcribe PATH [--language CODE]` turns a local audio file into text on CPU.
The language defaults to `en`; `--json` returns `transcript`. It does not log an
expense: Budget checks the transcript, asks about unclear amounts or currencies,
then uses `spend add`. The first use may download model weights. See the
[Budget reference](../agents/budget/TOOLS.md) for attachment handling and examples.

## Claude Code permissions

Each Claude folder contains `.claude/settings.json`. It allows only its listed launcher subcommands plus `WebSearch` and `WebFetch`. sh uses `Bash(../../bin/tripcrew ...)`; Windows uses `PowerShell(..\\..\\bin\\tripcrew.cmd ...)` in JSON, which decodes to single path separators. The `.cmd` launcher belongs in PowerShell, not as an unescaped Bash command.

Planner's `trip set` permission has an explicit deny for `--b*`, covering every argparse abbreviation of `--budget-sgd`, including `--b`. No bare `Bash`, `PowerShell`, interpreter, shell wrapper, `uv`, or launcher-wide wildcard is granted. JSON flags follow the subcommand to match the narrow prefixes.

These rules add pre-approvals; they are not an exclusive command sandbox. Auto mode can review other operations, and existing user/local/managed rules also apply. The installed `claude doctor` recognized both files but reported the workspace untrusted, ignoring Planner's 16 and Reel Adder's 22 allow entries. The owner must start Claude Code interactively and accept its workspace trust dialog before these grants activate. Confirm the setting sources and effective permissions with `/status` and `/permissions` in that session. The files do not select a bypass mode.

Syntax and scope checked against installed `claude --help` (2.1.312), [settings scope](https://code.claude.com/docs/en/settings) and [permission rules](https://code.claude.com/docs/en/permissions), 4 November 2026.

## Codex project config

[Budget config](../agents/budget/.codex/config.toml) uses `workspace-write` and `approval_policy = "never"`: commands run within the sandbox without approval prompts; forbidden operations fail. The only additional writable root is shared `state/`. Codex resolves `../../../state` from `agents/budget/.codex/`. Command network access is on, with the network proxy allowing only `api.frankfurter.dev` for FX. The sandbox remains enabled.

The environment settings reuse the prepared `tools/.venv`, disable uv syncing/downloads and persistent cache use, and suppress Python bytecode writes. They do not disable Python's FX HTTP requests. [uv environment-variable reference](https://docs.astral.sh/uv/reference/environment/).

On a fresh checkout, prepare dependencies **before** starting Budget, from the repository root:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
uv sync --project tools --locked --group dev
```

Codex supports per-folder config. It loads this project layer only for a **trusted project/worktree**. The owner must accept the trust prompt, or add this entry to their user-level `~/.codex/config.toml` using the actual absolute worktree root:

```toml
[projects.'C:\path\to\tripcrew-worktree']
trust_level = "trusted"
```

Trust cannot safely be self-declared by a repository's project config. No user-level config was changed. Switch must preserve the folder config and sandbox rather than pass conflicting launch flags. Check effective startup permissions: approval `never`, sandbox `workspace-write`, the resolved shared-state root and enabled FX proxy. Console Auto and provider approval policy are separate controls.

This is a filesystem/network boundary, not an enforcement of the Budget command lane: it can technically edit shared JSON. The reference documents only Budget operations. No whole-repository write grant or full-access bypass is added.

Checked against installed `codex --help` (0.163.0-alpha.11) and official OpenAI documentation: [project layers and relative paths](https://learn.chatgpt.com/docs/config-file/config-advanced), [trust and precedence](https://learn.chatgpt.com/docs/config-file/config-basic), [configuration keys](https://learn.chatgpt.com/docs/config-file/config-reference), [sandbox and network controls](https://learn.chatgpt.com/docs/agent-approvals-security), 4 November 2026. Managed requirements can constrain these settings. The installed CLI's home-directory error prevented a live config-load/sandbox test in this task; see [result.md](../result.md).

## Shared state and handoff

Launchers resolve `tools/` and the default repository `state/` from their own location. `TRIPCREW_STATE` overrides state; use an absolute path for isolated checks. Unset the test override in production so all three agents share the same state. Locking and atomic writes are provided by the CLI.

Reel Adder's reference records fetch, independent verification, wishlist addition, then identified; an unresolved clip goes through a question to the person before failed. The successful handoff names `planner` and `budget` in chat with the saved wishlist ID. No Telegram messages or relay events were sent during setup. Console settings, real Switch names, trust and live group routing remain owner setup, not verified delivery.
