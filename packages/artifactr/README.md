<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/artifactr/assets/brand/banner-dark.svg">
  <img alt="artifactr: people and agents editing the same artifacts, every change versioned and attributed." src="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/artifactr/assets/brand/banner-light.svg" width="100%">
</picture>

<p>
  <a href="https://artifactr.alexnodeland.com"><img alt="Docs" src="https://img.shields.io/badge/docs-artifactr.alexnodeland.com-2D2A8C"></a>
  <a href="https://github.com/alexnodeland/artifactr/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/alexnodeland/artifactr/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12, 3.13 and 3.14" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-2D2A8C">
  <img alt="Coverage: 100%" src="https://img.shields.io/badge/coverage-100%25-2D2A8C">
  <img alt="Typed: pyright strict" src="https://img.shields.io/badge/typed-pyright%20strict-2D2A8C">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-2D2A8C"></a>
</p>

**artifactr** is a Python library for chat applications in which people and agents work on the same documents, plans and specs, with every change versioned, attributed and fed back into the agent's context.

> **Status:** alpha. [0.1.0](https://github.com/alexnodeland/artifactr/releases/tag/v0.1.0) is the first release and delivers [RFC-0001](https://lattice.alexnodeland.com/artifactr/rfcs/0001-v0.1-implementation-plan/), the v0.1 plan. The API may still change before 1.0.

## Why

In most chat applications the conversation is the only channel. artifactr adds a second: artifacts that live beside the chat and that both sides edit directly. When a person rewrites a paragraph the agent drafted, or the agent restructures a plan, the edit says something about how each side is thinking. So every edit is versioned, attributed to whoever made it, visible to every participant, and told to the agent before it acts.

## Install

Python 3.12 or newer. artifactr is distributed as **`artifactr-ai`** and imported as `artifactr` (the name `artifactr` on PyPI is an unrelated project). Until it is on PyPI, install it from this repository:

```bash
uv add "artifactr-ai[fastapi] @ git+https://github.com/alexnodeland/artifactr"
```

Extras: `fastapi` (WebSocket and REST), `mcp` (external agents), `postgres` or `sqlite` (SQL storage with a driver), and `sql` (SQL storage without one).

## Example

A person edits a brief, then asks the agent for more. The agent is told about the edit before it starts, and its own edit is recorded the same way:

```python
import asyncio

from pydantic_ai import Agent

from artifactr import (
    ArtifactWorkspace,
    InMemoryStorage,
    MarkdownArtifact,
    Runner,
    Session,
    UserActor,
    Workspaces,
)
from artifactr.core import SetFocus


class Brief(MarkdownArtifact):  # an artifact type: a Pydantic model, registered as "brief"
    pass


agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[None],
    capabilities=[ArtifactWorkspace(types=[Brief])],  # tools, instructions and change notes
)
runner = Runner(agent, app=None)
workspaces = Workspaces(InMemoryStorage(), types=[Brief])


async def main() -> None:
    alice = UserActor(id="u_alice", name="Alice")
    ws = await workspaces.open("acme", "launch", actor=alice)
    thread = await ws.create_thread("Launch brief")

    await ws.create(Brief(text="# Launch\n\nWe ship on Friday."), artifact_id="brief")
    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("brief",)))

    brief = await ws.get(Brief, "brief")
    await ws.commit(brief.edit_text("Friday", "Monday"))  # version 2, by Alice

    sent = await runner.send(ws, thread.id, "Add a risks section to the brief.")
    if sent.run is not None:
        await sent.run.wait()  # the agent is told what Alice changed before it starts

    for envelope in await ws.read():
        print(envelope.seq, envelope.actor.kind, envelope.event.type)


asyncio.run(main())
```

It needs `ANTHROPIC_API_KEY`, or any other [pydantic-ai model](https://ai.pydantic.dev/models/). The log it prints shows Alice's edit, the agent's run, its tool call and its own edit, in order and attributed.

## Try it

[`examples/docplan`](https://github.com/alexnodeland/lattice/blob/main/examples/docplan/README.md) is a complete application built on the library: a person and an agent co-write a document and plan its work, over WebSocket, REST and MCP, with a terminal client.

```sh
make install
export ANTHROPIC_API_KEY=...
uv run docplan-serve            # in one terminal
uv run docplan --user alice     # in another
```

Set `DOCPLAN_DATABASE_URL` (for example `sqlite+aiosqlite:///docplan.db`) to keep its workspaces in a database instead of memory.

## What you get

- **Artifact types as Pydantic models.** Subclass `Artifact`; versioning, validation, patches, change summaries and agent tools come from the library.
- **One write path.** Every change, from any participant and any surface, is a command committed through a tenant-scoped workspace handle, checked against the artifact's version and appended to the workspace's ordered log.
- **Proposals that don't block.** Artifact types can make agents propose instead of edit; people accept, edit or reject whenever they like, and the agent hears the outcome.
- **An agent that follows along.** One pydantic-ai capability adds the artifact tools, instructions rendered fresh for every request, notes on what others changed, steering mid-run, and pauses for questions and approvals.
- **Live output apart from history.** Token-level output streams to watchers; the log holds only durable facts.
- **Surfaces that behave the same.** A WebSocket thread protocol and REST for your frontend, and MCP for external agents, all through one command handler.
- **Storage in memory, SQLite or PostgreSQL**, behind one protocol.
- **Rules you can read and port.** A pure, synchronous core pinned by language-neutral conformance fixtures, with 100% branch coverage and pyright strict.

## Documentation

The documentation site is at **<https://artifactr.alexnodeland.com>**. It is built from [`docs/`](https://lattice.alexnodeland.com/artifactr/) and published from `main` on every push; run `make docs-serve` to read it locally at <http://localhost:8000>.

- [Getting started](https://lattice.alexnodeland.com/artifactr/getting-started/) and the [guides](https://lattice.alexnodeland.com/artifactr/guides/artifact-types/): artifact types, workspaces, storage, the agent, live output, serving, MCP, security and testing.
- [Architecture](https://lattice.alexnodeland.com/artifactr/architecture/): concepts, layers, the write path, the agent, tenancy and concurrency.
- [Thread protocol v1](https://lattice.alexnodeland.com/artifactr/protocol/): the WebSocket, REST and MCP contracts, with a generated [JSON Schema](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/schemas/artifactr.v1.json).
- [Architecture decision records](https://lattice.alexnodeland.com/artifactr/adr/): why each part is the way it is.
- [RFCs](https://lattice.alexnodeland.com/artifactr/rfcs/): proposals and the v0.1 build plan.
- [Brand](https://lattice.alexnodeland.com/artifactr/assets/brand/): the mark, colours and type.

## Built on

[Pydantic](https://docs.pydantic.dev), [pydantic-ai](https://ai.pydantic.dev), [SQLAlchemy](https://www.sqlalchemy.org), [FastAPI](https://fastapi.tiangolo.com) and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## Contributing

See [CONTRIBUTING.md](https://github.com/alexnodeland/lattice/blob/main/CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/LICENSE)
