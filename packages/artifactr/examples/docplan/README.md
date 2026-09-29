# docplan

artifactr's reference implementation. A person and an agent write a document together and plan
the work it describes. The chat is one channel. The doc and the plan are the other: both sides
edit them, and each side sees the other's changes.

It is a small, complete application built only on artifactr's public API:

| Piece | File | What it shows |
|---|---|---|
| Artifact types | [`artifacts.py`](src/docplan/artifacts.py) | A Markdown `Doc`, and a `Plan` with `write_policy="propose"`, its own methods, `render_for_agent` and `describe_change` |
| Agent | [`agent.py`](src/docplan/agent.py) | A pydantic-ai agent with the `ArtifactWorkspace` capability, plus the plan's own tools |
| Server | [`app.py`](src/docplan/app.py) | FastAPI with the thread protocol over WebSocket, REST at `/v1`, and MCP at `/mcp`, over in-memory or SQL storage |
| Terminal client | [`cli.py`](src/docplan/cli.py) | A chat client that speaks the thread protocol |

## Run it

From the repository root, with an Anthropic key. To use another provider, set `DOCPLAN_MODEL` to
any [pydantic-ai model name](https://ai.pydantic.dev/models/), such as `openai:<model>`, and set
that provider's key.

```sh
uv sync --all-packages
export ANTHROPIC_API_KEY=...
uv run docplan-serve
```

In another terminal:

```sh
uv run docplan --user alice
```

```text
alice in main, thread thr_…. /help for commands.
> Draft a short launch doc for search, then plan the work.
alice: Draft a short launch doc for search, then plan the work.
docplan is working…
  · create_artifact {"kind": "doc", "data": {"title": "Search launch", "text": "…"}}
✚ docplan created doc art_1f…
  · create_artifact {"kind": "plan", "data": {"goal": "Ship search", "doc_id": "art_1f…"}}
? docplan proposes to create a plan
  /accept prp_9c… or /reject prp_9c…
docplan: I drafted the launch doc and proposed a plan for it.
> /accept prp_9c…
✚ alice created plan art_4d…
alice accepted prp_9c…
> Add a task for the announcement, owned by Sam.
…
? docplan proposes to edit art_4d…: added 'Write the announcement'
  /accept prp_2e… or /reject prp_2e…
```

The plan's write policy is `propose`, so the agent's changes to it wait for your review; the doc
it edits directly. Edit anything yourself and the agent sees what you changed on its next turn. When
the agent asks a question, your next message answers it.

The server listens on `DOCPLAN_HOST` and `DOCPLAN_PORT` (default `127.0.0.1:8000`).

### Keep workspaces in a database

By default everything lives in memory and is gone when the server stops. Set
`DOCPLAN_DATABASE_URL` to keep it in SQLite or PostgreSQL. The server migrates the database to
artifactr's schema when it starts.

```sh
DOCPLAN_DATABASE_URL=sqlite+aiosqlite:///docplan.db uv run docplan-serve
DOCPLAN_DATABASE_URL=postgresql+asyncpg://user:password@localhost/docplan uv run docplan-serve
```

### Client commands

| Input | Does |
|---|---|
| any text | Posts a message. The agent starts, or takes it as steering if it is already working |
| `/list` | Lists the workspace's artifacts |
| `/show ID` | Prints an artifact |
| `/accept ID` | Accepts a proposal |
| `/reject ID [REASON]` | Rejects a proposal, with an optional reason the agent will see |
| `/mode edit` or `/mode suggest` | In `suggest` mode every agent change becomes a proposal |
| `/rate 1-5 [COMMENT]` | Rates the agent's last turn, as typed feedback (a `rating`) |
| `/stop` | Stops the agent's current run |
| `/help` and `/quit` | Help, and leave |

Other flags: `--url` (default `http://127.0.0.1:8000`), `--workspace` (default `main`), `--thread`
to rejoin a thread, and `--send MESSAGE` (repeatable) to post messages, print what happens until
each run finishes, and exit.

### Observe it

docplan reports to OpenTelemetry when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, through
`artifactr.otel.configure_telemetry`: its turns, commits, model and tool calls, database queries and
HTTP requests as traces, artifactr's metrics, and its logs. With `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` (and `LANGFUSE_BASE_URL`) set too, it files each turn in Langfuse under its
thread and user, creates the score configs of its `rating` feedback, and mirrors the `main`
workspace's ratings to Langfuse scores on the rated turn's trace.

With a LiteLLM proxy at `DOCPLAN_LITELLM_URL`, the agent calls its model group
`DOCPLAN_LITELLM_MODEL` (`claude-sonnet` by default) with the key `DOCPLAN_LITELLM_KEY`, and every
request carries docplan's tenant, thread and trace.

[stackr](https://github.com/alexnodeland/stackr) runs the Collector, Grafana, Langfuse and LiteLLM.
With its stack running, start docplan on stackr's network from the repository root:

```sh
docker compose -f compose.yaml -f compose.stackr.yaml --profile app up -d --build
```

### Other surfaces

- **REST:** `curl -H 'x-user: alice' localhost:8000/v1/workspaces/main/artifacts`. See the
  [protocol](../../docs/protocol.md) for commands and reads.
- **MCP:** point an MCP client at `http://127.0.0.1:8000/mcp/`. It works in the `main`
  workspace like any other participant: artifacts are resources, and commands are tools.

Authentication is a demo: the server trusts the `x-user` header. Real applications resolve the
actor from their own sessions in `resolve_actor`.

## Test it

The tests run the whole stack with scripted models, so they need no API key:

```sh
uv run pytest examples/docplan/tests
```
