# The reference implementation

[`examples/docplan`](https://github.com/alexnodeland/artifactr/tree/main/examples/docplan) is a small, complete application built on artifactr: a person and an agent write a document together, then plan the work it describes. It uses only the library's public API, a test enforces that, and it is held to the same quality gates as the library ([ADR-0024](adr/0024-reference-implementation-as-a-workspace-member.md)). Read it when you want to see every piece of this documentation working together.

## What it contains

| Piece | Source | What it shows |
|---|---|---|
| Artifact types | [`artifacts.py`](https://github.com/alexnodeland/artifactr/blob/main/examples/docplan/src/docplan/artifacts.py) | A Markdown `Doc` the agent edits directly, and a `Plan` with `write_policy = "propose"`, its own methods, `render_for_agent` and `describe_change` |
| Agent | [`agent.py`](https://github.com/alexnodeland/artifactr/blob/main/examples/docplan/src/docplan/agent.py) | A pydantic-ai agent with the `ArtifactWorkspace` capability and `ask_user`, plus the plan's own tools, `add_task` and `set_task_status` |
| Server | [`app.py`](https://github.com/alexnodeland/artifactr/blob/main/examples/docplan/src/docplan/app.py) | A FastAPI app with the thread protocol and REST at `/v1`, MCP at `/mcp`, and in-memory or SQL storage |
| Terminal client | [`cli.py`](https://github.com/alexnodeland/artifactr/blob/main/examples/docplan/src/docplan/cli.py) | A chat client that speaks the thread protocol as plain JSON frames, a template for a client in any language; `/rate` gives typed feedback on a turn |
| Observability | [`app.py`](https://github.com/alexnodeland/artifactr/blob/main/examples/docplan/src/docplan/app.py) | `configure_telemetry` when an OTLP endpoint is set; Langfuse's turn context, score configs and a feedback mirror when its keys are set; a LiteLLM proxy when one is configured |
| Tests | [`tests/`](https://github.com/alexnodeland/artifactr/tree/main/examples/docplan/tests) | The real server and client over a real WebSocket, with a scripted model |

## Run it

docplan is a member of the repository's uv workspace, so it runs against the library in the same checkout. From the repository root, with an Anthropic API key:

```bash
make install                    # or: uv sync --all-packages
export ANTHROPIC_API_KEY=...
uv run docplan-serve            # in one terminal
uv run docplan --user alice     # in another
```

To use another provider, set `DOCPLAN_MODEL` to any [pydantic-ai model name](https://ai.pydantic.dev/models/) and that provider's key. The server listens on `127.0.0.1:8000`; set `DOCPLAN_HOST` and `DOCPLAN_PORT` to change it.

By default the server keeps its workspaces in memory, and they are gone when it stops. Set `DOCPLAN_DATABASE_URL` to keep them in SQLite or PostgreSQL with [SQL storage](guides/storage.md#sql-storage); the server migrates the database to artifactr's schema when it starts:

```bash
DOCPLAN_DATABASE_URL=sqlite+aiosqlite:///docplan.db uv run docplan-serve
DOCPLAN_DATABASE_URL=postgresql+asyncpg://user:password@localhost/docplan uv run docplan-serve
```

Then ask for a document and a plan. The agent edits the document directly; its changes to the plan arrive as proposals you accept with `/accept` or reject with `/reject`. Edit anything yourself and the agent is told what you changed on its next turn. When it asks a question, your next message answers it. The [docplan README](https://github.com/alexnodeland/artifactr/blob/main/examples/docplan/README.md) lists every client command and flag, and shows a sample session.

The same server speaks the other surfaces too: REST under `/v1` (the demo trusts an `x-user` header, as in `curl -H 'x-user: alice' localhost:8000/v1/workspaces/main/artifacts`), and MCP at `http://127.0.0.1:8000/mcp/` for external agents.

!!! warning "Demo authentication"

    docplan trusts whatever user the `x-user` header or `user` query parameter names, and puts everyone in one tenant. It shows where authentication plugs in, not how to do it. See [Multi-tenancy and security](guides/security.md).

## Test it

The tests run the whole stack with a scripted `FunctionModel`, so they need no API key:

```bash
uv run pytest examples/docplan/tests
```

[Testing your application](guides/testing.md) explains the pattern.

## How it maps to the guides

| docplan | Guide |
|---|---|
| `Doc` and `Plan` | [Defining artifact types](guides/artifact-types.md) |
| `build_agent`, `add_task`, `set_task_status` | [The agent](guides/agent.md) |
| `create_app`, `resolve_actor` | [Serving over WebSocket and REST](guides/serving.md) |
| `DOCPLAN_DATABASE_URL` and the storage it selects | [Storage](guides/storage.md) |
| `ArtifactrMcp` and `resolve_client` in `create_app` | [External agents over MCP](guides/mcp.md) |
| The terminal client | The [thread protocol](protocol.md) |
