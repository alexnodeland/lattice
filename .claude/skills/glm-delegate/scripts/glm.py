#!/usr/bin/env python3
"""Delegate a task to a GLM model on the Z.ai GLM Coding Plan, within its credit limits.

The worker is Claude Code itself, run headless against Z.ai's Anthropic-compatible
endpoint: that is the documented way to use the plan from Claude Code, so the
delegation stays inside the plan's "supported tools" rule.

    glm.py status                        # quota, peak window, what a run would pick
    glm.py run --mode code  "task..."    # GLM edits files in --cwd
    glm.py run --mode research "q..."    # GLM searches the web (Z.ai MCP), read-only
    glm.py run --mode ask   "prompt..."  # no tools: draft, summarize, transform
    glm.py ledger                        # what past runs cost

Stdlib only. Needs ZAI_API_KEY and the `claude` CLI on PATH.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ANTHROPIC_ENDPOINT = "https://api.z.ai/api/anthropic"
MONITOR_URL = "https://api.z.ai/api/monitor/usage"
SEARCH_MCP = "https://api.z.ai/api/mcp/web_search_prime/mcp"
READER_MCP = "https://api.z.ai/api/mcp/web_reader/mcp"

BEST = "glm-5.3"
FAST = "glm-5.3-flash"

# Credits per 10,000 tokens (docs.z.ai/devpack/overview, "Credit Calculation").
MULTIPLIERS = {
    BEST: {"input": 6.9, "cached": 1.7, "output": 24.0},
    FAST: {"input": 2.3, "cached": 0.56, "output": 8.0},
}
MCP_CALL_CREDITS = 1.2

# Lite plan allowance; the API reports percentages, these turn them into credits.
PLAN_CREDITS = {
    "lite": {"5h": 2_000, "week": 10_000},
    "pro": {"5h": 12_000, "week": 60_000},
    "max": {"5h": 28_000, "week": 140_000},
}

# Peak: Mon-Fri 14:00-18:00 Singapore time (UTC+8), billed at 1x; off-peak at 0.5x.
SGT = dt.timezone(dt.timedelta(hours=8))

# Guard thresholds, in percent of the window used. Overridable by env.
STOP_5H = float(os.environ.get("GLM_STOP_5H_PCT", 85))
STOP_WEEK = float(os.environ.get("GLM_STOP_WEEK_PCT", 90))
DOWNGRADE_5H = float(os.environ.get("GLM_DOWNGRADE_5H_PCT", 60))
DOWNGRADE_5H_PEAK = float(os.environ.get("GLM_DOWNGRADE_5H_PEAK_PCT", 40))
WEEK_PACE_SLACK = float(os.environ.get("GLM_WEEK_PACE_SLACK_PCT", 15))
MCP_RESERVE = int(os.environ.get("GLM_MCP_RESERVE", 10))

STATE_DIR = Path(os.environ.get("GLM_DELEGATE_HOME", Path.home() / ".cache" / "glm-delegate"))
LEDGER = STATE_DIR / "ledger.jsonl"
LOCK = STATE_DIR / "run.lock"

# Only these reach the worker: the parent's own Claude Code session variables
# (auth, session ids, remote-control sockets) must not leak into it.
PASSTHROUGH_ENV = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "TERM",
    "TMPDIR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "no_proxy",
    "NODE_EXTRA_CA_CERTS",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
)

WORKER_PROMPT = (
    "You are a worker delegated a task by another coding agent, who will review "
    "your output.\n"
    "- Do exactly the task; do not widen its scope.\n"
    "- Be economical: read only the files you need, and keep your output short.\n"
    "- End with a concise report: what you did (files changed, commands run), what you\n"
    "  found, and anything left uncertain or undone. No pleasantries."
)

RESEARCH_PROMPT = """You are a research worker delegated a question by another agent.
- You may make at most {searches} web searches in total (web reader fetches count too). Plan them.
- Prefer primary sources (official docs, release notes, papers, repositories).
- Answer with: a direct answer first, then key findings as bullets, each with its source URL,
  then what you could not confirm. Do not pad."""


def die(msg: str, code: int = 2) -> None:
    """Print an error message to stderr and exit."""
    print(f"glm-delegate: {msg}", file=sys.stderr)
    sys.exit(code)


def api_key() -> str:
    """Return the Z.ai API key from the environment."""
    key = os.environ.get("ZAI_API_KEY") or os.environ.get("Z_AI_API_KEY")
    if not key:
        die("ZAI_API_KEY is not set")
    return key


# ---------------------------------------------------------------- quota


def monitor_get(path: str, params: dict | None = None) -> dict | None:
    """GET one of the plan's usage-monitor endpoints and return its data, or None."""
    url = f"{MONITOR_URL}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key()}", "Accept-Language": "en-US,en"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"glm-delegate: {path} check failed ({exc})", file=sys.stderr)
        return None
    if not body.get("success"):
        print(f"glm-delegate: {path} check refused: {body.get('msg')}", file=sys.stderr)
        return None
    return body.get("data")


def fetch_quota() -> dict | None:
    """Fetch quota, reset windows, and MCP usage from the API."""
    data = monitor_get("quota/limit")
    if data is None:
        print("glm-delegate: quota unknown; using the local ledger only", file=sys.stderr)
        return None
    out = {"level": data.get("level", "lite"), "5h": None, "week": None, "mcp": None}
    for lim in data.get("limits", []):
        reset = lim.get("nextResetTime")
        entry = {"pct": float(lim.get("percentage", 0)), "reset_ms": reset}
        # unit 3 = hours, 6 = weeks, 5 = months (observed on the quota endpoint).
        if lim.get("type") == "TOKENS_LIMIT" and lim.get("unit") == 3:
            out["5h"] = entry
        elif lim.get("type") == "TOKENS_LIMIT" and lim.get("unit") == 6:
            out["week"] = entry
        elif lim.get("type") == "TIME_LIMIT":
            entry.update(remaining=lim.get("remaining"), total=lim.get("usage"))
            out["mcp"] = entry
    return out


def fetch_usage(hours: int) -> dict | None:
    """Fetch the plan's own meter of tokens per model and calls per MCP tool."""
    # The monitor takes and buckets times in China/Singapore time (UTC+8), by the hour.
    now = dt.datetime.now(SGT)
    params = {
        "startTime": (now - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:00:00"),
        "endTime": now.strftime("%Y-%m-%d %H:59:59"),
    }
    models = monitor_get("model-usage", params)
    tools = monitor_get("tool-usage", params)
    if models is None and tools is None:
        return None
    m_total = (models or {}).get("totalUsage") or {}
    t_total = (tools or {}).get("totalUsage") or {}
    return {
        "calls": m_total.get("totalModelCallCount", 0),
        "models": [(m["modelName"], m["totalTokens"]) for m in m_total.get("modelSummaryList", [])],
        "tools": [
            (t.get("toolNameI18n") or t["toolCode"], t["totalUsageCount"])
            for t in t_total.get("toolSummaryList", [])
        ],
    }


def is_peak(now: dt.datetime | None = None) -> bool:
    """Return True inside the weekday peak billing window."""
    now = (now or dt.datetime.now(dt.UTC)).astimezone(SGT)
    return now.weekday() < 5 and 14 <= now.hour < 18


def next_offpeak(now: dt.datetime | None = None) -> dt.datetime:
    """Return the next off-peak start (18:00 SGT) at or after now."""
    now = (now or dt.datetime.now(dt.UTC)).astimezone(SGT)
    return now.replace(hour=18, minute=0, second=0, microsecond=0)


def fmt_reset(ms: int | None) -> str:
    """Format a reset timestamp as a human-readable countdown."""
    if not ms:
        return "no window open"
    at = dt.datetime.fromtimestamp(ms / 1000, dt.UTC)
    left = at - dt.datetime.now(dt.UTC)
    hours = max(left.total_seconds(), 0) / 3600
    span = f"{hours:.1f}h" if hours < 48 else f"{hours / 24:.1f}d"
    return f"resets in {span} ({at:%a %H:%M} UTC)"


def week_elapsed_pct(q: dict) -> float | None:
    """Return the percentage of the quota week that has elapsed."""
    reset = (q.get("week") or {}).get("reset_ms")
    if not reset:
        return None
    left = reset / 1000 - time.time()
    return max(0.0, min(100.0, 100 * (1 - left / (7 * 86400))))


def decide(q: dict | None, mode: str, tier: str, force: bool) -> tuple[str | None, list[str]]:
    """Pick a model for this run, or None to refuse. Returns (model, reasons)."""
    reasons: list[str] = []
    wants = {"best": BEST, "fast": FAST}.get(tier) or (FAST if mode == "ask" else BEST)
    if q is None:
        reasons.append("quota unknown")
        return wants, reasons

    five = (q.get("5h") or {}).get("pct", 0.0)
    week = (q.get("week") or {}).get("pct", 0.0)
    if not force and five >= STOP_5H:
        reasons.append(
            f"5-hour window {five:.0f}% used (stop at {STOP_5H:.0f}%), "
            f"{fmt_reset(q['5h'].get('reset_ms'))}"
        )
        return None, reasons
    if not force and week >= STOP_WEEK:
        reasons.append(
            f"weekly quota {week:.0f}% used (stop at {STOP_WEEK:.0f}%), "
            f"{fmt_reset(q['week'].get('reset_ms'))}"
        )
        return None, reasons

    if wants == BEST and tier == "auto":
        peak = is_peak()
        elapsed = week_elapsed_pct(q)
        if five >= DOWNGRADE_5H:
            reasons.append(f"5-hour window {five:.0f}% used: using {FAST}")
            wants = FAST
        elif peak and five >= DOWNGRADE_5H_PEAK:
            reasons.append(f"peak hours (2x cost) and 5-hour window {five:.0f}% used: using {FAST}")
            wants = FAST
        elif elapsed is not None and week > elapsed + WEEK_PACE_SLACK:
            reasons.append(
                f"weekly quota {week:.0f}% used but only {elapsed:.0f}% of the week gone: "
                f"using {FAST}"
            )
            wants = FAST
    return wants, reasons


# ---------------------------------------------------------------- ledger


def credits_for(model_usage: dict, peak: bool) -> float:
    """Estimate credits from a run's per-model token usage."""
    total = 0.0
    for model, u in model_usage.items():
        m = MULTIPLIERS.get(model) or (
            MULTIPLIERS[FAST] if "flash" in model or "haiku" in model else MULTIPLIERS[BEST]
        )
        fresh = u.get("inputTokens", 0) + u.get("cacheCreationInputTokens", 0)
        total += (
            fresh * m["input"]
            + u.get("cacheReadInputTokens", 0) * m["cached"]
            + u.get("outputTokens", 0) * m["output"]
        ) / 10_000
    return total * (1.0 if peak else 0.5)


def ledger_append(entry: dict) -> None:
    """Append one run record to the ledger."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def ledger_read() -> list[dict]:
    """Return all ledger records, skipping unparseable lines."""
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text().splitlines():
        with contextlib.suppress(json.JSONDecodeError):
            rows.append(json.loads(line))
    return rows


def ledger_since(hours: float) -> float:
    """Return estimated credits spent over the last ``hours``."""
    cutoff = time.time() - hours * 3600
    return sum(r.get("credits_est", 0) for r in ledger_read() if r.get("ts", 0) >= cutoff)


@contextlib.contextmanager
def single_run():
    """Lite is sized for one project at a time: serialize delegations."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("glm-delegate: another delegation is running; waiting for it...", file=sys.stderr)
            fcntl.flock(f, fcntl.LOCK_EX)
        yield


# ---------------------------------------------------------------- commands


def cmd_status(args: argparse.Namespace) -> None:
    """Print quota, peak window, and the model each mode would use."""
    q = fetch_quota()
    peak = is_peak()
    print(
        f"time: {'PEAK (1x credits)' if peak else 'off-peak (0.5x credits)'}"
        + (f"; off-peak again at {next_offpeak():%H:%M} SGT" if peak else "")
    )
    if q:
        plan = PLAN_CREDITS.get(q["level"], PLAN_CREDITS["lite"])
        print(f"plan: {q['level']}")
        for key, label in (("5h", "5-hour"), ("week", "weekly")):
            lim = q.get(key)
            if lim:
                left = plan[key] * (1 - lim["pct"] / 100)
                print(
                    f"{label}: {lim['pct']:.0f}% used, ~{left:,.0f} credits left, "
                    f"{fmt_reset(lim['reset_ms'])}"
                )
        elapsed = week_elapsed_pct(q)
        if elapsed is not None:
            print(f"week pace: {elapsed:.0f}% of the week elapsed")
        if q.get("mcp"):
            m = q["mcp"]
            print(
                f"web search/reader calls: {m.get('remaining')} of {m.get('total')} left "
                f"this month, {fmt_reset(m['reset_ms'])}"
            )
    usage = fetch_usage(args.hours)
    if usage:
        span = f"{args.hours}h" if args.hours < 48 else f"{args.hours / 24:.0f}d"
        models = ", ".join(f"{name} {tokens:,} tokens" for name, tokens in usage["models"])
        print(f"last {span} (Z.ai meter): {models or 'no model use'}; {usage['calls']} calls")
        if usage["tools"]:
            print("  tools: " + ", ".join(f"{name} {n}" for name, n in usage["tools"]))
    print(
        f"ledger: ~{ledger_since(5):.0f} credits in the last 5h, "
        f"~{ledger_since(168):.0f} in the last 7d (estimated)"
    )
    for mode in ("code", "research", "ask"):
        model, why = decide(q, mode, "auto", False)
        print(f"{mode:>8} -> {model or 'REFUSE'}" + (f"  ({'; '.join(why)})" if why else ""))


def read_prompt(args: argparse.Namespace) -> str:
    """Assemble the prompt from --prompt-file, arguments, or stdin."""
    parts = []
    if args.prompt_file:
        parts.append(Path(args.prompt_file).read_text())
    if args.prompt:
        parts.append(" ".join(args.prompt))
    if not parts and not sys.stdin.isatty():
        parts.append(sys.stdin.read())
    prompt = "\n\n".join(p.strip() for p in parts if p.strip())
    if not prompt:
        die("no prompt given (argument, --prompt-file, or stdin)")
    return prompt


def worker_env(model: str) -> dict:
    """Build the environment for the worker subprocess."""
    env = {k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ}
    if "NODE_EXTRA_CA_CERTS" not in env and Path("/root/.ccr/ca-bundle.crt").exists():
        env["NODE_EXTRA_CA_CERTS"] = "/root/.ccr/ca-bundle.crt"
    env.update(
        ANTHROPIC_BASE_URL=ANTHROPIC_ENDPOINT,
        ANTHROPIC_AUTH_TOKEN=api_key(),
        ANTHROPIC_MODEL=model,
        # Anything the worker routes to an Anthropic tier name still lands on GLM.
        ANTHROPIC_DEFAULT_OPUS_MODEL=model,
        ANTHROPIC_DEFAULT_SONNET_MODEL=model,
        ANTHROPIC_DEFAULT_HAIKU_MODEL=FAST,
        API_TIMEOUT_MS="3000000",
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
        DISABLE_AUTOUPDATER="1",
    )
    return env


def cmd_run(args: argparse.Namespace) -> None:
    """Delegate a task to GLM and record the run in the ledger."""
    claude = shutil.which("claude")
    if not claude:
        die("the `claude` CLI is not on PATH")
    prompt = read_prompt(args)
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        die(f"--cwd {cwd} is not a directory")

    with single_run():
        before = fetch_quota()
        model, reasons = decide(before, args.mode, args.tier, args.force)
        for r in reasons:
            print(f"glm-delegate: {r}", file=sys.stderr)
        if model is None:
            die(
                "refusing to run to stay inside the plan limits "
                "(use --force to override, or do the task yourself)",
                3,
            )

        cmd = [
            claude,
            "-p",
            "--model",
            model,
            "--output-format",
            "json",
            "--max-turns",
            str(args.max_turns),
            "--no-session-persistence",
            "--setting-sources",
            "",
            "--strict-mcp-config",
        ]
        system = WORKER_PROMPT
        mcp_file = None

        if args.mode == "ask":
            cmd += ["--tools", ""]
        elif args.mode == "code":
            tools = ["Read", "Write", "Edit", "Glob", "Grep"]
            allowed = list(tools)
            if args.allow_bash:
                tools.append("Bash")
                allowed += [f"Bash({p})" for p in args.allow_bash]
            cmd += [
                "--permission-mode",
                "acceptEdits",
                "--tools",
                ",".join(tools),
                "--allowedTools",
                *allowed,
            ]
        elif args.mode == "research":
            searches = args.max_searches
            mcp = (before or {}).get("mcp") or {}
            remaining = mcp.get("remaining")
            if remaining is not None:
                searches = min(searches, max(0, remaining - MCP_RESERVE))
            tools = ["Read", "Glob", "Grep"]
            cmd += ["--tools", ",".join(tools)]
            if searches > 0:
                cfg = {
                    "mcpServers": {
                        "zai-search": {
                            "type": "http",
                            "url": SEARCH_MCP,
                            "headers": {"Authorization": f"Bearer {api_key()}"},
                        },
                        "zai-reader": {
                            "type": "http",
                            "url": READER_MCP,
                            "headers": {"Authorization": f"Bearer {api_key()}"},
                        },
                    }
                }
                fd, mcp_file = tempfile.mkstemp(prefix="glm-mcp-", suffix=".json")
                with os.fdopen(fd, "w") as f:
                    json.dump(cfg, f)
                os.chmod(mcp_file, 0o600)
                cmd += [
                    "--mcp-config",
                    mcp_file,
                    "--allowedTools",
                    *tools,
                    "mcp__zai-search",
                    "mcp__zai-reader",
                ]
                system = RESEARCH_PROMPT.format(searches=searches)
            else:
                print(
                    "glm-delegate: monthly web search budget is spent; researching from "
                    "model knowledge and local files only",
                    file=sys.stderr,
                )
                system = (
                    RESEARCH_PROMPT.format(searches=0)
                    + "\n- You have no web access: say so, and answer from what you know."
                )
        if args.system:
            system += "\n" + args.system
        # The prompt goes on stdin: --allowedTools is variadic and would swallow a positional.
        cmd += ["--append-system-prompt", system]

        peak = is_peak()
        started = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=worker_env(model),
                input=prompt,
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            die(f"worker timed out after {args.timeout}s; check {cwd} for partial edits", 4)
        finally:
            if mcp_file:
                os.unlink(mcp_file)

        result = None
        for line in reversed(proc.stdout.strip().splitlines()):
            with contextlib.suppress(json.JSONDecodeError):
                result = json.loads(line)
                break
        if result is None:
            sys.stderr.write(proc.stderr[-4000:])
            die(f"worker produced no result (exit {proc.returncode})", 4)

        usage = result.get("modelUsage") or {}
        searches_used = sum(u.get("webSearchRequests", 0) for u in usage.values())
        credits = credits_for(usage, peak)
        mcp_after = None
        after = fetch_quota()
        if after and before and after.get("mcp") and before.get("mcp"):
            mcp_after = after["mcp"].get("remaining")
            calls = (before["mcp"].get("remaining") or 0) - (mcp_after or 0)
            searches_used = max(searches_used, calls)
        credits += searches_used * MCP_CALL_CREDITS

        entry = {
            "ts": started,
            "mode": args.mode,
            "model": model,
            "peak": peak,
            "cwd": str(cwd),
            "turns": result.get("num_turns"),
            "secs": round(time.time() - started),
            "ok": not result.get("is_error"),
            "credits_est": round(credits, 1),
            "mcp_calls": searches_used,
            "denied": sorted(
                {d.get("tool_name", "?") for d in result.get("permission_denials") or []}
            ),
            "usage": {
                m: {
                    k: u.get(k, 0)
                    for k in (
                        "inputTokens",
                        "cacheReadInputTokens",
                        "cacheCreationInputTokens",
                        "outputTokens",
                    )
                }
                for m, u in usage.items()
            },
            "task": prompt[:200],
        }
        ledger_append(entry)

        if args.json:
            print(
                json.dumps(
                    {**entry, "result": result.get("result"), "quota_after": after}, indent=2
                )
            )
        else:
            print(result.get("result") or "(no text result)")
            line = (
                f"\n--- glm-delegate: {model}, {entry['turns']} turns, {entry['secs']}s, "
                f"~{credits:.0f} credits ({'peak' if peak else 'off-peak'})"
            )
            if after and after.get("5h") and after.get("week"):
                line += f"; 5h {after['5h']['pct']:.0f}% / week {after['week']['pct']:.0f}% used"
            if entry["denied"]:
                n = len(result["permission_denials"])
                line += f"; {n} tool calls DENIED ({', '.join(entry['denied'])})"
            if result.get("subtype") == "error_max_turns":
                line += f"; STOPPED at --max-turns {args.max_turns}, work may be incomplete"
            print(line)
        if result.get("is_error"):
            sys.exit(1)


def cmd_ledger(args: argparse.Namespace) -> None:
    """Print recent delegations and their estimated credits."""
    rows = ledger_read()[-args.n :]
    if not rows:
        print("no delegations recorded yet")
        return
    for r in rows:
        when = dt.datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
        print(
            f"{when}  {r['mode']:<8} {r['model']:<14} ~{r['credits_est']:>6.1f} cr  "
            f"{r.get('turns')} turns  {'ok ' if r.get('ok') else 'ERR'}  {r['task'][:60]!r}"
        )
    print(f"total ~{sum(r['credits_est'] for r in rows):.0f} credits over {len(rows)} runs")


def main() -> None:
    """Parse arguments and dispatch the subcommand."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="quota, recent usage, and the model each mode would use")
    st.add_argument(
        "--hours", type=int, default=24, help="usage window from Z.ai's meter (max 720 = 30d)"
    )

    r = sub.add_parser("run", help="delegate a task to GLM")
    r.add_argument("prompt", nargs="*", help="the task (or use --prompt-file / stdin)")
    r.add_argument("--prompt-file")
    r.add_argument("--mode", choices=("code", "research", "ask"), default="code")
    r.add_argument(
        "--tier",
        choices=("auto", "best", "fast"),
        default="auto",
        help=f"auto: {BEST} for code/research, {FAST} for ask, downgraded under quota pressure",
    )
    r.add_argument("--cwd", default=".", help="directory the worker runs in (code mode edits here)")
    r.add_argument(
        "--allow-bash",
        action="append",
        metavar="PATTERN",
        help='let the worker run matching commands, e.g. "pytest:*" '
        'or "uv run pytest:*" (repeatable)',
    )
    r.add_argument("--max-turns", type=int, default=30)
    r.add_argument(
        "--max-searches", type=int, default=6, help="research mode: web search/reader call cap"
    )
    r.add_argument("--timeout", type=int, default=1800, help="seconds")
    r.add_argument("--system", help="extra instructions appended to the worker's system prompt")
    r.add_argument("--force", action="store_true", help="run even past the stop thresholds")
    r.add_argument("--json", action="store_true", help="machine-readable output")

    lg = sub.add_parser("ledger", help="recent delegations and their estimated credits")
    lg.add_argument("-n", type=int, default=20)

    args = p.parse_args()
    {"status": cmd_status, "run": cmd_run, "ledger": cmd_ledger}[args.cmd](args)


if __name__ == "__main__":
    main()
