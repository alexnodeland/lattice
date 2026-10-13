---
name: glm-delegate
description: Delegate self-contained coding, research, or bulk text tasks to GLM models (GLM-5.3 / GLM-5.3-Flash) on the user's Z.ai GLM Coding Plan, keeping within its 5-hour and weekly credit limits. Use when a task is well-specified and parallelizable or mechanical (writing tests, boilerplate, contained refactors, migrations across many files, docs), when it needs web research the user would rather not spend Claude usage on, or for bulk summarizing/drafting/transforming text, and whenever the user asks to use GLM, Z.ai, or "the coding plan". Do not use for tasks needing this conversation's context, judgment calls, or anything touching secrets, credentials, or production.
---

# GLM delegate

Hands a task to a GLM worker and gets back its report. The worker is Claude Code
itself, run headless against Z.ai's Anthropic-compatible endpoint
(`https://api.z.ai/api/anthropic`), which is the documented way to use the GLM
Coding Plan from Claude Code. The plan's terms limit it to supported tools, so
don't call the coding endpoint from other scripts.

Everything runs through one script, which needs `ZAI_API_KEY` and `claude` on PATH:

```bash
G=.claude/skills/glm-delegate/scripts/glm.py
python3 $G status [--hours 168]                    # quota, usage by model/tool, model picks
python3 $G run --mode code     [opts] "task"       # edits files in --cwd
python3 $G run --mode research [opts] "question"   # web search, read-only
python3 $G run --mode ask      [opts] "prompt"     # no tools
python3 $G ledger                                  # what past runs cost
```

## Models and the plan

| Model | Use for | Credits per 10k tokens (in / cached / out) |
|---|---|---|
| `glm-5.3` (best) | code, research, anything that needs reasoning | 6.9 / 1.7 / 24 |
| `glm-5.3-flash` (fast) | summarizing, drafting, reformatting, classifying, simple edits | 2.3 / 0.56 / 8 |

The Lite plan gives **2,000 credits per 5 hours** and **10,000 per week**.
**Peak hours** (Mon–Fri 14:00–18:00 SGT = 06:00–10:00 UTC) bill at 1x and
off-peak at 0.5x. Web search and web reader calls cost 1.2 credits each and are
also capped per month (100 on Lite). Other plan models (GLM-5.2, 5.1, 4.7) are
routed to these two server-side, and `glm-5.3-flashx` isn't on Lite.

Measured costs off-peak: a small coding task costs about 3 credits, a focused
research question about 4, and a flash `ask` under 1. A 25-turn lint cleanup
of one 600-line file cost about 85, because every turn resends the context.
**Turns are what cost**, so set `--max-turns` tightly and ask for batched edits.
The ledger's estimates run about 1.4x higher than Z.ai's meter, and the live
percentages from `status` are authoritative.

## How the script keeps you in budget

Before each run it reads the live quota (`/api/monitor/usage/quota/limit`) and:

- **Refuses** if the 5-hour window is ≥85% used or the week is ≥90% used (exit 3). `--force` overrides this; use it only if the user asks.
- **Downgrades** `--tier auto` runs from glm-5.3 to flash when the 5-hour window is ≥60% used, when it's peak time and the window is ≥40% used, or when weekly use is more than 15 points ahead of the week's elapsed fraction.
- **Caps web calls** in research mode at `--max-searches` (default 6), leaving a reserve of 10 monthly calls.
- **Runs one delegation at a time** (Lite is sized for one project), and later calls wait for the lock.
- **Logs** each run's estimated credits to `~/.cache/glm-delegate/ledger.jsonl` and prints the quota afterwards.

`status` also reports Z.ai's own meter for the last `--hours` (default 24): tokens
per model and calls per MCP tool, from the same monitor endpoints as Z.ai's
`glm-plan-usage` plugin. That plugin only works when Claude Code itself runs on
GLM, which is why this skill doesn't depend on it.

You can tune the thresholds with the env vars `GLM_STOP_5H_PCT`, `GLM_STOP_WEEK_PCT`,
`GLM_DOWNGRADE_5H_PCT`, `GLM_DOWNGRADE_5H_PEAK_PCT`, `GLM_WEEK_PACE_SLACK_PCT` and `GLM_MCP_RESERVE`.

## When to delegate

Delegate when the task is **self-contained** (a fresh agent can do it from the prompt
plus the repo) and **checkable** (you can verify the result cheaply with a diff,
tests, or sources). Good fits:

- writing or extending tests for a named module; boilerplate; a contained refactor; applying one pattern across many files
- "find out X" research: library versions, API behaviour, comparing options, reading docs
- bulk text work: summarize these logs, draft docstrings, convert formats (use `ask`, which picks flash)

Keep it yourself when it needs this conversation's context or the user's
preferences, a design decision, security-sensitive code, secrets, deploys, or
anything you can't verify. Also keep it when it's quicker to do than to describe.

## Writing the task

The worker sees only your prompt and the files in `--cwd`, so write the task the way you'd brief a contractor:

- the goal, and the exact files or directories in scope
- constraints: style to match, what not to touch, and the commands that define "done"
- what the report should contain

For long tasks, write the prompt to a file in the scratchpad and pass `--prompt-file`.

## Options

- `--cwd DIR`: where the worker runs. In code mode it **edits files there**. For risky or exploratory work, point it at a git worktree or a scratch copy.
- The worker **cannot edit anything under `.claude/`**, because Claude Code treats it as sensitive and denies the edit. It also can't edit other protected paths. Edit those yourself, or have it work on a copy in the scratchpad.
- `--allow-bash PATTERN` (repeatable, code mode): lets the worker run matching commands, using Claude Code permission syntax such as `"uv run pytest:*"`, `"bun test:*"`, or `"ruff check:*"`. Without it the worker can only read and edit files. Never allow broad patterns like `"*"`, network tools, `git push`, or installs.
- `--tier best|fast`: override the automatic model pick. Use `fast` for mechanical work even in code mode.
- `--max-turns N` (default 30): bounds cost. Use 8–15 for small tasks. A run that stops at the limit says so.
- `--max-searches N`: the research web-call budget.
- `--system "..."`: adds extra worker instructions.
- `--json`: returns structured output (result, credits, quota after).

## After a run

1. Read the worker's report, but don't take it on trust. If the footer says tool calls were **DENIED** or the run **STOPPED at --max-turns**, the work is likely incomplete.
2. **Code mode:** review `git diff` in `--cwd` yourself, run the tests/lint yourself, and fix or revert what's wrong. You remain responsible for the change.
3. **Research mode:** spot-check the claims that matter against their cited URLs before relying on them.
4. Tell the user you delegated, which model ran, and roughly what it cost (the script's last line has this).

If the script refuses (exit 3), tell the user which limit was hit and when it
resets (`status` shows this), then do the task yourself or wait. Don't loop
retries, and don't use `--force` on your own.

## Running several tasks

The lock runs delegations one after another, so you can queue independent tasks
from background shells without overrunning Lite's concurrency. Run `status`
between batches. During peak hours, prefer `--tier fast`, or defer
non-urgent large jobs until off-peak, when they cost half as much.
